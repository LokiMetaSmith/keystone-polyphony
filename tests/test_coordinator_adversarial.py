"""Adversarial regressions for durable execution and admission provenance."""

import asyncio
from pathlib import Path
import secrets
import subprocess
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp.test_utils import TestClient, TestServer
from src.liminal_bridge.coordinator import Coordinator, Conflict, select_task
from src.liminal_bridge.coordinator_service import create_app
from src.liminal_bridge.worker import Worker
from src.liminal_bridge.worktree_adapter import GitWorktreeAdapter


@pytest.fixture
def store(tmp_path):
    return Coordinator(tmp_path / "coordinator.db")


def task(store, **kwargs):
    return store.enroll(
        "example", "approved revision one", ["check"], reviewers=["reviewer"], **kwargs
    )


def submit(store, t, worker="author"):
    a = store.start_attempt(t["id"], worker, [], 10, secrets.token_hex(16))
    artifact = store.save_work(a["id"], worker, "approved patch")
    c = store.candidate(a["id"], worker, "1" * 40, artifact)
    store.evidence(c["id"], "reviewer", "check", True, 1)
    return a, c


@pytest.mark.asyncio
async def test_cancel_completed_attempt_does_not_signal_reaped_pid(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (
        ["init", "-q"],
        ["config", "user.name", "Review"],
        ["config", "user.email", "review@example.invalid"],
    ):
        subprocess.run(["git", "-C", str(repo), *args], check=True)
    (repo / "README").write_text("baseline")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "baseline"], check=True)
    adapter = GitWorktreeAdapter(repo, tmp_path / "worktrees")
    aid = secrets.token_hex(16)
    await adapter.launch(aid, "HEAD", [sys.executable, "-c", "pass"], 5, env={})
    result = await adapter.wait(aid)
    assert result["termination_confirmed"]
    # A late retry must return the saved result. Never send a signal to a PID
    # that has already been reaped and may now name an unrelated process group.
    with patch("src.liminal_bridge.worktree_adapter.os.killpg") as signal_group:
        assert await adapter.cancel(aid) == result
    signal_group.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_attempt_does_not_block_independent_work_for_same_worker(store):
    blocked = task(store)
    a = store.start_attempt(blocked["id"], "author", [], 10, "first")
    store.observe(a["id"], "unknown")
    independent = task(store)
    snapshot = store.snapshot()
    assert select_task(snapshot, [], 10)["id"] == independent["id"]
    client = MagicMock()
    client.snapshot = AsyncMock(return_value=snapshot)

    async def call(op, **payload):
        assert op == "start_attempt"
        return store.start_attempt(worker="author", **payload)

    client.call = AsyncMock(side_effect=call)
    client.request = AsyncMock(return_value={"state": "submitted"})
    worker = Worker(client, "author", seconds=10)
    assert await worker.tick() == "started"
    assert client.call.await_args.kwargs["task_id"] == independent["id"]


def test_revised_dependency_blocks_dependent_acceptance(store):
    dependency = task(store)
    _, dc = submit(store, dependency)
    store.accept(dc["id"])
    dependent = task(store, dependencies=[dependency["id"]])
    _, candidate = submit(store, dependent, worker="second-author")
    store.revise(
        dependency["id"], 1, "changed dependency contract", ["check"], ["reviewer"]
    )
    assert (
        next(t for t in store.snapshot()["task"] if t["id"] == dependency["id"])[
            "status"
        ]
        == "todo"
    )
    with pytest.raises(Conflict):
        store.accept(candidate["id"])


@pytest.mark.asyncio
async def test_revised_task_revokes_reserved_launch(store, tmp_path):
    t = task(store)
    a = store.start_attempt(t["id"], "author", [], 30, "reserve")
    store.revise(t["id"], 1, "different approved revision two", ["check"], ["reviewer"])
    adapter = MagicMock()
    adapter.root = tmp_path
    credentials = {"a" * 32: {"identity": "author", "role": "worker"}}
    execution = {"base": "HEAD", "command": ["approved-command"], "env": {}}
    with patch(
        "src.liminal_bridge.coordinator_service.run_attempt",
        new=AsyncMock(return_value={}),
    ) as launched:
        async with TestClient(
            TestServer(create_app(store, credentials, adapter, execution))
        ) as client:
            response = await client.post(
                "/execute",
                json={"attempt_id": a["id"]},
                headers={"Authorization": "Bearer " + "a" * 32},
            )
            await response.read()
            await asyncio.sleep(0)
            assert response.status == 409
            launched.assert_not_awaited()


def test_dependency_reacceptance_requires_new_candidate_and_review(store):
    dependency = task(store)
    da, dc = submit(store, dependency)
    store.observe(da["id"], "exited", True)
    store.accept(dc["id"])
    dependent = task(store, dependencies=[dependency["id"]])
    attempt, old = submit(store, dependent, worker="second-author")
    store.observe(attempt["id"], "exited", True)
    original = store.accept(old["id"])
    assert original["candidate"]["dependency_admissions"]
    store.evidence(
        dc["id"], "reviewer", "check", False, 1, request_key="dependency-fail"
    )
    with pytest.raises(Conflict):
        store.admission(old["id"])
    store.evidence(
        dc["id"], "reviewer", "check", True, 1, request_key="dependency-pass"
    )
    store.accept(dc["id"])
    with pytest.raises(Conflict):
        store.accept(old["id"])
    new_attempt, new = submit(store, dependent, worker="third-author")
    assert new["id"] != old["id"]
    assert store.accept(new["id"])["candidate"]["id"] == new["id"]
    # Accepted historical packets cannot be exported after transitive revocation.
    leaf = task(store, dependencies=[dependent["id"]])
    _, lc = submit(store, leaf, worker="leaf-author")
    store.accept(lc["id"])
    store.revise(dependency["id"], 1, "new contract", ["check"], ["reviewer"])
    for cid in (dc["id"], new["id"], lc["id"]):
        with pytest.raises(Conflict):
            store.admission(cid)


def test_legacy_dependent_admission_fails_closed_without_provenance(store):
    dep = task(store)
    _, dc = submit(store, dep)
    store.accept(dc["id"])
    dependent = task(store, dependencies=[dep["id"]])
    _, c = submit(store, dependent, worker="dependent")
    packet = store.accept(c["id"])
    with store.transaction() as db:
        old = dict(packet)
        old["candidate"] = dict(packet["candidate"])
        old["candidate"].pop("dependency_admissions")
        store._save(db, "admission", c["id"], old)
    with pytest.raises(Conflict):
        store.admission(c["id"])


def test_cancelled_attempt_cannot_write_or_acquire(store):
    t = task(store, resource="shared")
    a = store.start_attempt(t["id"], "author", [], 30, "reserve")
    store.authorize_launch(a["id"], "author")
    store.acquire("shared", a["id"], "author", 0)
    store.request_cancel(a["id"], "author")
    with pytest.raises(Conflict):
        store.write_resource("shared", a["id"], "author", 1, "new-write", 1)
    with pytest.raises(Conflict):
        store.execution_permission(a["id"], "author")
    # Observation cannot silently discard a persisted cancellation request.
    assert store.observe(a["id"], "running")["state"] == "cancel_requested"


def test_cancel_before_dispatch_confirms_no_process_and_prevents_launch(store):
    t = task(store)
    a = store.start_attempt(t["id"], "author", [], 30, "reserve")
    result = store.request_cancel(a["id"], "author")
    assert result["termination_confirmed"]
    with pytest.raises(Conflict):
        store.authorize_launch(a["id"], "author")
    assert store.request_cancel(a["id"], "author") == result


@pytest.mark.asyncio
async def test_cancel_during_git_preparation_never_starts_command(tmp_path):
    import threading

    adapter = GitWorktreeAdapter(tmp_path, tmp_path / "worktrees")
    entered, released = threading.Event(), threading.Event()

    def prepare(path, base):
        entered.set()
        assert released.wait(3)
        path.mkdir()
        return "base"

    adapter._prepare = prepare
    aid = secrets.token_hex(16)
    launch = asyncio.create_task(
        adapter.launch(aid, "HEAD", [sys.executable, "-c", "pass"], 10)
    )
    await asyncio.to_thread(entered.wait, 2)
    pending = await adapter.cancel(aid)
    assert pending["state"] == "unknown"
    assert not pending["termination_confirmed"]
    released.set()
    with pytest.raises(Conflict):
        await launch
    result = await adapter.observe(aid)
    assert result["termination_confirmed"] and result["not_started"]
    with patch("src.liminal_bridge.worktree_adapter.subprocess.Popen") as process:
        with pytest.raises(Conflict):
            await adapter.launch(aid, "HEAD", ["unused"], 10)
        process.assert_not_called()


@pytest.mark.asyncio
async def test_launch_preparation_uses_original_time_budget(tmp_path):
    import time

    adapter = GitWorktreeAdapter(tmp_path, tmp_path / "worktrees")

    def prepare(path, base):
        time.sleep(0.06)
        path.mkdir()
        return "base"

    adapter._prepare = prepare
    aid = secrets.token_hex(16)
    with patch("src.liminal_bridge.worktree_adapter.subprocess.Popen") as process:
        with pytest.raises(Conflict):
            await adapter.launch(aid, "HEAD", ["unused"], 0.02)
        process.assert_not_called()
    assert (await adapter.observe(aid))["termination_confirmed"]


@pytest.mark.asyncio
async def test_group_cleanup_keeps_leader_unreaped_and_confirms_descendants_dead(
    tmp_path,
):
    import os

    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (
        ["init", "-q"],
        ["config", "user.name", "Review"],
        ["config", "user.email", "review@example.invalid"],
    ):
        subprocess.run(["git", "-C", str(repo), *args], check=True)
    (repo / "README").write_text("base")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
    adapter = GitWorktreeAdapter(repo, tmp_path / "worktrees")
    aid = secrets.token_hex(16)
    command = """import os,time
from pathlib import Path
reader,writer=os.pipe()
pid=os.fork()
if pid:
 os.close(writer);os.read(reader,1);os._exit(0)
os.close(reader)
Path('descendant.pid').write_text(str(os.getpid()))
os.write(writer,b'x')
while True:
 with open('progress.txt','a') as f:f.write('progress\\n')
 time.sleep(0.005)
"""
    signal_group = os.killpg
    signals = []

    def owned_signal(pid, sig):
        # Raising ChildProcessError here would prove PID reuse was possible.
        os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        signals.append(pid)
        return signal_group(pid, sig)

    with patch(
        "src.liminal_bridge.worktree_adapter.os.killpg", side_effect=owned_signal
    ):
        await adapter.launch(aid, "HEAD", [sys.executable, "-c", command], 5)
        result = await adapter.wait(aid)
    assert result["termination_confirmed"] and signals
    child = int((adapter._path(aid) / "descendant.pid").read_text())
    stat = Path(f"/proc/{child}/stat")
    if stat.exists():
        assert stat.read_text().rpartition(")")[2].split()[0] == "Z"
    with patch("src.liminal_bridge.worktree_adapter.os.killpg") as stale:
        assert await adapter.cancel(aid) == result
        stale.assert_not_called()


@pytest.mark.asyncio
async def test_revision_changed_during_preparation_prevents_worker_spawn(
    store, tmp_path
):
    import threading
    from src.liminal_bridge.worktree_adapter import run_attempt

    t = task(store)
    attempt = store.start_attempt(t["id"], "author", [], 10, "reserve")
    adapter = GitWorktreeAdapter(tmp_path, tmp_path / "worktrees")
    entered, released = threading.Event(), threading.Event()

    def prepare(path, base):
        entered.set()
        assert released.wait(3)
        path.mkdir()
        return "base"

    adapter._prepare = prepare
    execution = asyncio.create_task(
        run_attempt(store, adapter, attempt, "HEAD", ["unused"])
    )
    await asyncio.to_thread(entered.wait, 2)
    store.revise(t["id"], 1, "new approved requirements", ["check"], ["reviewer"])
    released.set()
    with patch("src.liminal_bridge.worktree_adapter.subprocess.Popen") as spawn:
        with pytest.raises(Conflict):
            await execution
        spawn.assert_not_called()
    assert store.snapshot()["attempt"][0]["termination_confirmed"]


@pytest.mark.asyncio
async def test_rpc_invalid_input_is_rejected_without_changing_reservations(store):
    credentials = {
        "a" * 32: {"identity": "author", "role": "worker"},
        "o" * 32: {"identity": "owner", "role": "owner"},
    }
    t = task(store)
    attempt = store.start_attempt(t["id"], "author", [], 10, "reserve")
    async with TestClient(TestServer(create_app(store, credentials))) as client:
        header = {"Authorization": "Bearer " + "a" * 32}
        for endpoint in ["/execute", "/cancel", "/call/start_attempt"]:
            assert (await client.post(endpoint, json=[], headers=header)).status in {
                400,
                403,
            }
        assert (await client.get("/events?after=bad", headers=header)).status == 400
        invalid_work = await client.post(
            "/call/save_work",
            json={"attempt_id": attempt["id"], "content": 123},
            headers=header,
        )
        assert invalid_work.status == 400
        assert not store.snapshot()["work"]
        assert (
            await client.get("/snapshot", headers={"Authorization": "Bearer é"})
        ).status == 401
        result = await client.post(
            "/call/observe",
            json={
                "attempt_id": attempt["id"],
                "state": "exited",
                "termination_confirmed": "false",
            },
            headers={"Authorization": "Bearer " + "o" * 32},
        )
        assert result.status == 400
    assert not store.snapshot()["attempt"][0]["termination_confirmed"]


def test_wall_clock_rollback_never_revives_permission_or_advice(tmp_path):
    wall, mono = [100.0], [50.0]
    authority = Coordinator(
        tmp_path / "clock.db",
        clock=lambda: wall[0],
        monotonic_clock=lambda: mono[0],
        boot_id="boot-one",
    )
    t = task(authority, resource="shared")
    a = authority.start_attempt(t["id"], "author", [], 10, "reserve")
    authority.acquire("shared", a["id"], "author", 0, seconds=5)
    advice = authority.advise(t["id"], "conductor", "optional", ttl=5)
    wall[0], mono[0] = 90, 56
    with pytest.raises(Conflict):
        authority.write_resource("shared", a["id"], "author", 1, "expired", 1)
    with pytest.raises(Conflict):
        authority.respond(advice["id"], "author", "follow", "too late")
    assert authority.remaining_seconds(a["id"], "author") == 4
    mono[0] = 61
    with pytest.raises(Conflict):
        authority.execution_permission(a["id"], "author")
    reopened = Coordinator(
        authority.path,
        clock=lambda: wall[0],
        monotonic_clock=lambda: mono[0],
        boot_id="boot-one",
    )
    with pytest.raises(Conflict):
        reopened.execution_permission(a["id"], "author")
    assert not reopened.snapshot()["resource"][0]["lease_current"]


def test_reboot_revokes_active_permission_but_keeps_saved_work(tmp_path):
    first = Coordinator(
        tmp_path / "boot.db",
        clock=lambda: 100,
        monotonic_clock=lambda: 50,
        boot_id="first",
    )
    t = task(first)
    a = first.start_attempt(t["id"], "author", [], 10, "reserve")
    artifact = first.save_work(a["id"], "author", "retained")
    restarted = Coordinator(
        first.path, clock=lambda: 100, monotonic_clock=lambda: 1, boot_id="second"
    )
    with pytest.raises(Conflict):
        restarted.execution_permission(a["id"], "author")
    assert restarted.artifact(artifact) == "retained"
    assert not restarted.snapshot()["attempt"][0]["termination_confirmed"]


@pytest.mark.asyncio
async def test_worker_cancels_expired_unlaunched_reservation_before_retry(store):
    t = task(store)
    a = store.start_attempt(t["id"], "author", [], 10, "reserve")
    store.monotonic_clock = lambda: a["monotonic_deadline"] + 1
    client = MagicMock()
    client.snapshot = AsyncMock(return_value=store.snapshot())
    client.request = AsyncMock()
    client.call = AsyncMock()
    assert await Worker(client, "author", seconds=10).tick() == "waiting_for_work"
    client.request.assert_awaited_once_with("POST", "/cancel", {"attempt_id": a["id"]})
    client.call.assert_not_called()


@pytest.mark.parametrize("base", ["HEAD", "main", "abc", "", 123])
def test_mutable_or_partial_base_cannot_define_a_reviewed_candidate(store, base):
    t = task(store)
    a = store.start_attempt(t["id"], "author", [], 10, "reserve")
    artifact = store.save_work(a["id"], "author", "immutable bytes")
    with pytest.raises(ValueError):
        store.candidate(a["id"], "author", base, artifact)
    assert not store.snapshot()["candidate"]


def test_old_review_response_cannot_override_later_failed_observation(store):
    t = task(store)
    a = store.start_attempt(t["id"], "author", [], 10, "start")
    artifact = store.save_work(a["id"], "author", "patch")
    c = store.candidate(a["id"], "author", "1" * 40, artifact)
    original = store.evidence(
        c["id"], "reviewer", "check", True, 1, request_key="first"
    )
    packet = store.accept(c["id"])
    assert store.evidence(c["id"], "reviewer", "check", True, 1) == original
    assert store.admission(c["id"]) == packet
    store.evidence(c["id"], "reviewer", "check", False, 1, request_key="second")
    assert (
        store.evidence(c["id"], "reviewer", "check", True, 1, request_key="first")
        == original
    )
    with pytest.raises(Conflict):
        store.accept(c["id"])
    with pytest.raises(Conflict):
        store.evidence(c["id"], "reviewer", "check", True, 1)
    with pytest.raises(Conflict):
        store.evidence(c["id"], "reviewer", "check", False, 1, request_key="first")
    assert len(store.snapshot()["evidence"]) == 2


def test_shared_dependency_dag_validation_is_bounded(store, monkeypatch):
    nodes = []
    for _ in range(12):
        current = task(store, dependencies=[t["id"] for t in nodes])
        _, c = submit(store, current)
        store.accept(c["id"])
        nodes.append(current)
    last = store.snapshot()["task"]
    candidate = next(t for t in last if t["id"] == nodes[-1]["id"])["accepted"]
    calls = [0]
    original = store._get

    def counted(*args):
        calls[0] += 1
        return original(*args)

    monkeypatch.setattr(store, "_get", counted)
    assert store.admission(candidate)["candidate"]["id"] == candidate
    assert calls[0] < 300


def test_invalid_legacy_admission_is_not_a_ready_dependency(store):
    root = task(store)
    _, c = submit(store, root)
    store.accept(c["id"])
    with store.transaction() as db:
        packet = store._get(db, "admission", c["id"])
        packet["candidate"]["base"] = "HEAD"
        store._save(db, "admission", c["id"], packet)
    task(store, dependencies=[root["id"]])
    independent = task(store)
    snapshot = store.snapshot()
    assert (
        next(t for t in snapshot["task"] if t["id"] == root["id"])["status"]
        == "blocked"
    )
    assert select_task(snapshot, [], 10)["id"] == independent["id"]


@pytest.mark.asyncio
async def test_live_waitid_child_runs_to_completion_before_supervisor_cleanup(tmp_path):
    """WNOWAIT/WNOHANG returns None for a live child on supported CPython/Linux."""
    import os

    adapter = GitWorktreeAdapter(tmp_path, tmp_path / "worktrees")
    aid = secrets.token_hex(16)
    marker = tmp_path / "completed.txt"
    with (tmp_path / "child.log").open("wb") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import sys,time; from pathlib import Path; time.sleep(0.15); "
                "Path(sys.argv[1]).write_text('completed')",
                str(marker),
            ],
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
        adapter.running[aid] = process
        assert (
            os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            is None
        )
        await adapter._supervise(
            aid, process, asyncio.get_running_loop().time() + 5, log
        )
    result = await adapter.observe(aid)
    assert result["termination_confirmed"] and result["returncode"] == 0
    assert marker.read_text() == "completed"
    assert not adapter.running


@pytest.mark.asyncio
async def test_wait_failure_preserves_original_error_and_execution_reservation(store):
    from src.liminal_bridge.worktree_adapter import run_attempt

    t = task(store)
    attempt = store.start_attempt(t["id"], "author", [], 10, "reserve")
    adapter = MagicMock()
    adapter.launch = AsyncMock(return_value={"base": "1" * 40})
    original = RuntimeError("adapter wait failed")
    adapter.wait = AsyncMock(side_effect=original)
    with pytest.raises(RuntimeError) as raised:
        await run_attempt(store, adapter, attempt, "HEAD", ["unused"])
    assert raised.value is original
    assert not store.snapshot()["attempt"][0]["termination_confirmed"]
