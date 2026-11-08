"""Issue #95 adversarial protocol tests; pass limits in docs/durable-collaboration.md."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import sys
from unittest.mock import AsyncMock

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
import pytest

from src.liminal_bridge.coordinator import Conflict, Coordinator, digest, select_task
from src.liminal_bridge.coordinator_service import create_app, CoordinatorClient
from src.liminal_bridge.worker import Worker, advise_from_problems
from src.liminal_bridge.worktree_adapter import GitWorktreeAdapter, run_attempt


@pytest.fixture
def store(tmp_path):
    return Coordinator(tmp_path / "authority.db")


def enroll(store, **kwargs):
    return store.enroll(
        "task", "requirements v1", ["tests"], reviewers=["reviewer"], **kwargs
    )


def start(store, task, worker="author", seconds=10, key="start"):
    return store.start_attempt(task["id"], worker, [], seconds, key)


def candidate(store, task=None, worker="author", patch="patch", base="base"):
    task = task or enroll(store)
    attempt = start(store, task, worker)
    artifact = store.save_work(attempt["id"], worker, patch)
    return store.candidate(attempt["id"], worker, base, artifact)


def test_atomic_fence_and_retry_survive_restart(store):
    now = [100.0]
    store.clock = lambda: now[0]
    task = enroll(store, resource="shared")
    a = start(store, task)

    def race(_):
        try:
            return store.acquire("shared", a["id"], "author", 0, seconds=2)
        except Conflict:
            return None

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(race, range(2)))
    assert all(r["fence"] == 1 for r in results)
    assert results[0] == results[1]
    effect = store.write_resource(
        "shared", a["id"], "author", 1, "write", {"change": 1}
    )
    now[0] += 3
    lease = store.acquire("shared", a["id"], "author", 1, seconds=2)
    assert lease["fence"] == 2
    other = enroll(store, resource="shared")
    rival = start(store, other, worker="rival")
    with pytest.raises(Conflict):
        store.acquire("shared", rival["id"], "rival", 2)
    with pytest.raises(Conflict):
        store.write_resource("shared", a["id"], "author", 1, "stale", 2)
    now[0] += 3
    replacement = store.acquire("shared", rival["id"], "rival", 2, seconds=2)
    assert replacement["fence"] == 3
    with pytest.raises(Conflict):
        store.write_resource("shared", a["id"], "author", 2, "late-worker", 3)
    restarted = Coordinator(store.path, clock=store.clock)
    assert (
        restarted.write_resource("shared", a["id"], "author", 1, "write", {"change": 1})
        == effect
    )
    with pytest.raises(Conflict):
        restarted.write_resource("shared", a["id"], "author", 1, "write", {"change": 2})
    with restarted.connect() as db:
        assert len(restarted._all(db, "effect")) == 1
        assert restarted._get(db, "destination", "shared") == effect


def test_unknown_execution_reserves_task_and_budget_is_task_wide(store):
    task = enroll(store, max_attempts=2, budget_seconds=20)
    a = start(store, task)
    store.clock = lambda: a["deadline"] + 100
    store.observe(a["id"], "cancel_requested")
    independent = enroll(store)
    assert (
        select_task(store.snapshot(), [], 10, now=store.clock())["id"]
        == independent["id"]
    )
    with pytest.raises(Conflict, match="termination unknown"):
        start(store, task, "replacement")
    artifact = store.save_work(a["id"], "author", "salvaged patch")
    reopened = Coordinator(store.path, clock=store.clock)
    assert reopened.artifact(artifact) == "salvaged patch"
    reopened.observe(a["id"], "exited", True)
    b = start(reopened, task, "replacement")
    reopened.observe(b["id"], "exited", True)
    with pytest.raises(Conflict, match="budget exhausted"):
        start(reopened, task, "third")


def test_start_retry_does_not_allocate_twice(store):
    task = enroll(store)
    a = start(store, task)
    assert start(store, task) == a
    with pytest.raises(Conflict, match="payload changed"):
        start(store, task, seconds=11)
    assert store.snapshot()["task"][0]["attempts"] == 1


def test_candidate_identity_and_evidence_fail_closed(store):
    task = enroll(store)
    c = candidate(store, task)
    with pytest.raises(Conflict, match="missing or failed"):
        store.accept(c["id"])
    with pytest.raises(Conflict):
        store.evidence(c["id"], "author", "tests", True, 1)
    store.evidence(c["id"], "reviewer", "tests", False, 1)
    with pytest.raises(Conflict):
        store.accept(c["id"])
    store.evidence(c["id"], "reviewer", "tests", True, 1)
    packet = store.accept(c["id"])
    assert packet["release_authorized"] is False
    assert store.accept(c["id"]) == packet
    assert len(store.snapshot()["evidence"]) == 2
    assert Coordinator(store.path).admission(c["id"]) == packet
    # A new failing observation withdraws admission until checks pass again.
    store.evidence(c["id"], "reviewer", "tests", False, 1)
    with pytest.raises(Conflict):
        store.admission(c["id"])
    store.evidence(c["id"], "reviewer", "tests", True, 1)
    store.accept(c["id"])
    artifact2 = store.save_work(c["attempt"], "author", "changed patch")
    c2 = store.candidate(c["attempt"], "author", c["base"], artifact2)
    assert c2["id"] != c["id"]
    with pytest.raises(Conflict):
        store.accept(c2["id"])
    store.revise(task["id"], 1, "requirements v2", ["tests"], ["reviewer"])
    with pytest.raises(Conflict):
        store.accept(c["id"])
    with pytest.raises(Conflict):
        store.evidence(c["id"], "reviewer", "tests", True, 1)
    with pytest.raises(Conflict):
        store.admission(c["id"])
    assert digest(["ab", "c"]) != digest(["a", "bc"])


def test_resource_permission_and_deadline(store):
    task = enroll(store, resource="shared")
    a = start(store, task)
    with pytest.raises(Conflict):
        store.acquire("other", a["id"], "author", 0)
    with pytest.raises(Conflict):
        store.acquire("shared", a["id"], "impostor", 0)
    store.acquire("shared", a["id"], "author", 0)
    store.clock = lambda: a["deadline"]
    with pytest.raises(Conflict):
        store.write_resource("shared", a["id"], "author", 1, "write", 1)


def test_choice_busy_dependency_capability_and_fairness(store):
    now = [1000]
    store.clock = lambda: now[0]
    old = enroll(store, priority=0)
    now[0] += 121
    high = enroll(store, priority=2, resource="shared")
    a = start(store, high)
    store.acquire("shared", a["id"], "author", 0)
    enroll(store, resource="shared")
    enroll(store, required=["gpu"])
    enroll(store, dependencies=[high["id"]])
    assert select_task(store.snapshot(), [], 10, now=now[0])["id"] == old["id"]
    # Aged task still wins over fresh high-priority work even without contention.
    enroll(store, priority=2)
    assert select_task(store.snapshot(), [], 10, now=now[0])["id"] == old["id"]


def test_advice_is_optional_expiring_and_rate_limited(store):
    task = enroll(store)
    advice = store.advise(task["id"], "conductor", "try another task")
    response = store.respond(
        advice["id"], "author", "decline", "independent work ready"
    )
    assert response["cause"] == "independent work ready"
    with pytest.raises(Conflict, match="rate limited"):
        store.advise(task["id"], "conductor", "repeated message")
    store.clock = lambda: advice["expires"]
    with pytest.raises(Conflict, match="expired"):
        store.respond(advice["id"], "author", "follow", "too late")
    assert start(store, task)  # no conductor permission needed


@pytest.fixture
def credentials():
    return {
        letter * 32: {"identity": identity, "role": role}
        for letter, identity, role in (
            ("o", "owner", "owner"),
            ("a", "author", "worker"),
            ("b", "second", "worker"),
            ("r", "reviewer", "reviewer"),
            ("s", "author", "reviewer"),
            ("c", "conductor", "conductor"),
        )
    }


@pytest.mark.asyncio
async def test_service_auth_identity_and_event_recovery(store, credentials):
    async with TestClient(TestServer(create_app(store, credentials))) as client:
        assert (await client.get("/snapshot")).status == 401

        async def call(op, payload, token):
            return await client.post(
                "/call/" + op,
                json=payload,
                headers={"Authorization": "Bearer " + token * 32},
            )

        task = enroll(store)
        c = candidate(store, task)
        assert (await call("accept", {"candidate_id": c["id"]}, "a")).status == 403
        assert (
            await call(
                "evidence",
                {
                    "candidate_id": c["id"],
                    "reviewer": "reviewer",
                    "check": "tests",
                    "passed": True,
                    "input_revision": 1,
                },
                "a",
            )
        ).status == 403
        assert (
            await call(
                "evidence",
                {
                    "candidate_id": c["id"],
                    "check": "tests",
                    "passed": True,
                    "input_revision": 1,
                },
                "s",
            )
        ).status == 409
        assert (
            await call(
                "evidence",
                {
                    "candidate_id": c["id"],
                    "check": "tests",
                    "passed": True,
                    "input_revision": 1,
                },
                "r",
            )
        ).status == 200
        assert (await call("accept", {"candidate_id": c["id"]}, "o")).status == 200
        assert (await call("revise", {}, "c")).status == 403
        assert (
            await call(
                "advise",
                {"task_id": task["id"], "message": "spam", "minimum_interval": 0.001},
                "c",
            )
        ).status == 400
        cursor = store.cursor()

        async def update():
            await asyncio.sleep(0.05)
            enroll(store)

        updater = asyncio.create_task(update())
        response = await client.get(
            f"/events?after={cursor}&timeout=0.8",
            headers={"Authorization": "Bearer " + "a" * 32},
        )
        assert (await response.json())["cursor"] > cursor
        await updater


@pytest.fixture
def repository(tmp_path):
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (
        ["init", "-q"],
        ["config", "user.name", "Test"],
        ["config", "user.email", "test@example.invalid"],
    ):
        subprocess.run(["git", "-C", str(repo), *args], check=True)
    (repo / "README").write_text("base\n")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
    return repo


@pytest.mark.asyncio
async def test_adapter_preserves_partial_work_on_timeout(store, repository, tmp_path):
    adapter = GitWorktreeAdapter(repository, tmp_path / "worktrees")
    task = enroll(store)
    a = start(store, task, seconds=0.4)
    result = await run_attempt(
        store,
        adapter,
        a,
        "HEAD",
        [
            sys.executable,
            "-c",
            "from pathlib import Path; import time; Path('partial.txt').write_text('saved'); time.sleep(10)",
        ],
    )
    assert result["execution"]["state"] == "timed_out"
    assert result["execution"]["termination_confirmed"]
    patch = Coordinator(store.path).artifact(result["candidate"]["patch"])
    assert "partial.txt" in patch and "+saved" in patch
    assert (repository / "partial.txt").exists() is False
    import subprocess

    subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "worktree",
            "remove",
            "--force",
            str(adapter._path(a["id"])),
        ],
        check=True,
    )
    assert Coordinator(store.path).artifact(result["candidate"]["patch"]) == patch
    restarted = GitWorktreeAdapter(repository, tmp_path / "worktrees")
    assert (await restarted.cancel(a["id"]))["termination_confirmed"] is False
    assert adapter.query_capabilities()["cost"] is None


@pytest.mark.asyncio
async def test_two_workers_without_conductor_and_with_busy_resource(
    store, repository, tmp_path, credentials
):
    adapter = GitWorktreeAdapter(repository, tmp_path / "worktrees")
    # Two independent tasks, plus a protected task whose resource is busy.
    holder = enroll(store, resource="shared")
    a = start(store, holder, worker="holder")
    store.acquire("shared", a["id"], "holder", 0)
    blocked = enroll(store, resource="shared")
    one, two = enroll(store), enroll(store)
    config = {
        "base": "HEAD",
        "command": [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('result.txt').write_text('done')",
        ],
        "env": {},
    }
    async with TestServer(create_app(store, credentials, adapter, config)) as server:
        url = str(server.make_url("")).rstrip("/")
        wa = Worker(CoordinatorClient(url, "a" * 32), "author", seconds=2)
        wb = Worker(CoordinatorClient(url, "b" * 32), "second", seconds=2)
        assert await wa.tick() == "started"
        assert await wb.tick() == "started"
        for _ in range(100):
            if len(store.snapshot()["candidate"]) == 2:
                break
            await asyncio.sleep(0.02)
        snapshot = store.snapshot()
        assert {c["task"] for c in snapshot["candidate"]} == {one["id"], two["id"]}
        assert (
            next(t for t in snapshot["task"] if t["id"] == blocked["id"])["attempts"]
            == 0
        )
        assert all(c["author"] in {"author", "second"} for c in snapshot["candidate"])
        # A conductor may observe a problem, but cannot assign/complete tasks.
        store.problem(wa.attempt, "author", "needs review")
        await advise_from_problems(CoordinatorClient(url, "c" * 32))
        assert store.snapshot()["advice"]


@pytest.mark.asyncio
async def test_legacy_completion_and_picker_cannot_bypass_managed(
    store, tmp_path, monkeypatch
):
    from src.liminal_bridge import server
    from src.liminal_bridge.dashboard import DashboardServer
    from src.liminal_bridge.mesh import LiminalMesh
    from src.liminal_bridge.storage import SQLiteStorageProvider

    task = enroll(store)
    mesh = LiminalMesh(
        "test",
        storage_provider=SQLiteStorageProvider(":memory:"),
        identity_path=str(tmp_path / "identity.pem"),
    )
    mesh.running = True
    mesh.warmup_complete = True
    mesh.release_baton = AsyncMock()
    mesh._send_to_sidecar = AsyncMock()
    await mesh.update_set("swarm_backlog", json.dumps({**task, "status": "todo"}))
    monkeypatch.setattr(server, "mesh", mesh)
    assert "coordinator" in (await server.complete_task(task["id"])).lower()
    mesh.release_baton.assert_not_called()
    assert await mesh.autonomously_pick_task() is None
    dashboard = object.__new__(DashboardServer)
    dashboard.mesh = mesh
    request = AsyncMock()
    request.json.return_value = {"action": "complete", "task_id": task["id"]}
    assert (await dashboard.handle_post_backlog(request)).status == 409
    # A stripped schema marker cannot bypass the reserved namespace guard.
    assert "coordinator" in (await server.complete_task("task_v2_unseen")).lower()


def test_competing_acquisitions_and_evidence_are_serialized(store):
    a = start(store, enroll(store, resource="shared"), "alice")
    b = start(store, enroll(store, resource="shared"), "bob")

    def acquire(attempt):
        try:
            return store.acquire("shared", attempt["id"], attempt["worker"], 0)
        except Conflict:
            return None

    with ThreadPoolExecutor(2) as pool:
        leases = list(pool.map(acquire, [a, b]))
    assert sum(lease is not None for lease in leases) == 1
    task = enroll(store)
    c = candidate(store, task)

    def review(passed):
        return store.evidence(c["id"], "reviewer", "tests", passed, 1)

    with ThreadPoolExecutor(2) as pool:
        observations = list(pool.map(review, [True, False]))
    assert {e["observation_revision"] for e in observations} == {1, 2}
    assert len(store.snapshot()["evidence"]) == 2
    # Identical retry keys from different authenticated principals are distinct.
    task1, task2 = enroll(store), enroll(store)
    first = start(store, task1, "worker1", key="same-key")
    second = start(store, task2, "worker2", key="same-key")
    assert first["id"] != second["id"]


@pytest.mark.asyncio
async def test_execute_retry_and_storage_outage_do_not_duplicate_or_abandon(
    store, repository, tmp_path, credentials, monkeypatch
):
    import sqlite3

    adapter = GitWorktreeAdapter(repository, tmp_path / "worktrees")
    execution = {
        "base": "HEAD",
        "command": [
            sys.executable,
            "-c",
            "from pathlib import Path; import time; time.sleep(0.15); Path('proof.txt').write_text('done')",
        ],
        "env": {},
    }
    task = enroll(store)
    attempt = start(store, task, seconds=10)
    observed = store.observe

    def transient(aid, state, termination_confirmed=False):
        if state == "running":
            raise sqlite3.OperationalError("temporary coordinator outage")
        return observed(aid, state, termination_confirmed)

    monkeypatch.setattr(store, "observe", transient)
    async with TestClient(
        TestServer(create_app(store, credentials, adapter, execution))
    ) as client:

        async def execute():
            response = await client.post(
                "/execute",
                json={"attempt_id": attempt["id"]},
                headers={"Authorization": "Bearer " + "a" * 32},
            )
            assert response.status == 200, await response.text()
            return await response.json()

        responses = await asyncio.gather(execute(), execute())
        assert responses[0] == responses[1]
        for _ in range(100):
            if store.snapshot()["candidate"]:
                break
            await asyncio.sleep(0.02)
        assert len(adapter.running) == 1
        assert len(store.snapshot()["candidate"]) == 1
        assert "proof.txt" in store.artifact(store.snapshot()["candidate"][0]["patch"])


@pytest.mark.asyncio
async def test_idle_worker_waits_without_inference_and_launch_recovery_is_fail_closed(
    store, credentials
):
    from unittest.mock import MagicMock

    client = MagicMock()
    client.snapshot = AsyncMock(return_value=store.snapshot())
    client.call = AsyncMock()
    worker = Worker(client, "author")
    assert await worker.tick() == "waiting_for_work"
    client.call.assert_not_called()
    task = enroll(store)
    attempt = start(store, task)
    store.observe(attempt["id"], "unknown")
    # Restarted service cannot retry an unknown launch, even with same request.
    adapter = MagicMock()
    async with TestClient(
        TestServer(
            create_app(
                store, credentials, adapter, {"base": "HEAD", "command": ["unused"]}
            )
        )
    ) as http:
        response = await http.post(
            "/execute",
            json={"attempt_id": attempt["id"]},
            headers={"Authorization": "Bearer " + "a" * 32},
        )
        assert response.status == 409
        assert store.snapshot()["attempt"][0]["termination_confirmed"] is False


def test_pending_review_is_not_repeated_and_old_candidate_cannot_complete(store):
    task = enroll(store)
    c = candidate(store, task)
    store.observe(c["attempt"], "exited", True)
    assert select_task(store.snapshot(), [], 10) is None
    with pytest.raises(Conflict, match="awaiting review"):
        start(store, task, worker="replacement")
    store.evidence(c["id"], "reviewer", "tests", True, 1)
    changed = store.save_work(c["attempt"], "author", "new patch")
    c2 = store.candidate(c["attempt"], "author", "base", changed)
    with pytest.raises(Conflict, match="superseded"):
        store.accept(c["id"])
    with pytest.raises(Conflict, match="missing or failed"):
        store.accept(c2["id"])
    store.evidence(c2["id"], "reviewer", "tests", False, 1)
    assert select_task(store.snapshot(), [], 10)["id"] == task["id"]
    store.evidence(c2["id"], "reviewer", "tests", True, 1)
    store.accept(c2["id"])


@pytest.mark.asyncio
async def test_network_outage_holds_protected_calls_but_approved_work_finishes(
    store, repository, tmp_path, credentials
):
    from aiohttp import ClientError

    adapter = GitWorktreeAdapter(repository, tmp_path / "worktrees")
    execution = {
        "base": "HEAD",
        "command": [
            sys.executable,
            "-c",
            "from pathlib import Path; import time; time.sleep(0.2); Path('offline.txt').write_text('preserved')",
        ],
        "env": {},
    }
    enroll(store)
    runner = web.AppRunner(create_app(store, credentials, adapter, execution))
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    client = CoordinatorClient(f"http://127.0.0.1:{port}", "a" * 32)
    worker = Worker(client, "author", seconds=2)
    try:
        assert await worker.tick() == "started"
        await site.stop()
        with pytest.raises(ClientError):
            await client.call(
                "write_resource",
                resource="shared",
                attempt_id=worker.attempt,
                fence=1,
                retry_key="offline",
                value="forbidden",
            )
        for _ in range(100):
            if store.snapshot()["candidate"]:
                break
            await asyncio.sleep(0.02)
        assert len(store.snapshot()["candidate"]) == 1
        assert not store.snapshot()["destination"]
        assert store.snapshot()["task"][0]["attempts"] == 1
    finally:
        await runner.cleanup()
