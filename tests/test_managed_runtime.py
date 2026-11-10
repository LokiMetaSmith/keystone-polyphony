"""Canonical external execution, authenticated HTTP and recovery boundaries."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json

from aiohttp.test_utils import TestClient, TestServer
import pytest

from src.core.collaboration.authority import Conflict, Coordinator
from src.liminal_bridge.coordinator_service import create_app
from src.liminal_bridge.managed_cli import service_url, submit

REPOSITORY = "github:github.com/example/project"
OTHER = "github:github.com/example/other"
BASE = "a" * 40
SCOPE = {"deployment_id": "installation-one", "repository": REPOSITORY}
TOKENS = {
    name: name.ljust(40, "-")
    for name in (
        "owner",
        "ingress",
        "runtime",
        "worker",
        "reviewer",
        "self-review",
        "foreign",
    )
}


@pytest.fixture
def config():
    policy = {
        "checks": ["tests"],
        "reviewers": ["independent-review", "trusted-runtime"],
        "max_attempts": 3,
        "budget_seconds": 300,
        "profiles": {
            "approved": {
                "base": BASE,
                "attempt_seconds": 60,
                "capabilities": ["python"],
            }
        },
    }
    return {
        "schema_version": 1,
        "deployment_id": SCOPE["deployment_id"],
        "repositories": {REPOSITORY: policy, OTHER: copy.deepcopy(policy)},
    }


@pytest.fixture
def credentials():
    def principal(identity, role, repository=REPOSITORY):
        return {
            "identity": identity,
            "role": role,
            "deployment_id": SCOPE["deployment_id"],
            "repositories": [repository],
        }

    return {
        TOKENS["owner"]: {"identity": "host-owner", "role": "owner"},
        TOKENS["worker"]: {"identity": "old-worker", "role": "worker"},
        TOKENS["ingress"]: principal("issue-ingress", "ingress"),
        TOKENS["runtime"]: principal("trusted-runtime", "runtime"),
        TOKENS["reviewer"]: principal("independent-review", "reviewer"),
        TOKENS["self-review"]: principal("trusted-runtime", "reviewer"),
        TOKENS["foreign"]: principal("another-runtime", "runtime", OTHER),
    }


def source_payload(**changes):
    return {
        "schema_version": 1,
        **SCOPE,
        "source": "github:issue:19",
        "request_key": "explicit-run-one",
        "title": "Implement the bounded change",
        "requirements": "Write a tested change to the fixture repository.",
        **changes,
    }


def enroll(store, config, **changes):
    payload = source_payload(**changes)
    payload.pop("schema_version")
    return store.managed_enroll(
        **payload, policy=config["repositories"][payload["repository"]]
    )


def claim(store, config, task_id, **changes):
    payload = {
        **SCOPE,
        "runtime_principal": "trusted-runtime",
        "worker_id": "immutable-worker-one",
        "profile": "approved",
        "profile_spec": config["repositories"][REPOSITORY]["profiles"]["approved"],
        "task_id": task_id,
        "request_key": "launch-one",
        "base": BASE,
        **changes,
    }
    return store.managed_claim(**payload)


def capture(store, attempt_id, **changes):
    artifacts = {}
    for kind, content in (
        ("patch", "diff --git a/a b/a\n"),
        ("log", "Tests executed by the guest, not independent review."),
        ("manifest", json.dumps({"workspace_archive_sha256": "b" * 64})),
    ):
        result = store.managed_capture(
            **SCOPE,
            runtime_principal="trusted-runtime",
            attempt_id=attempt_id,
            kind=kind,
            content=content,
            **changes,
        )
        assert result["artifact_id"] == hashlib.sha256(content.encode()).hexdigest()
        artifacts[kind] = result["artifact_id"]
    return artifacts


def terminal(store, attempt_id, artifacts, **changes):
    return store.managed_observe(
        **SCOPE,
        runtime_principal="trusted-runtime",
        attempt_id=attempt_id,
        **{
            "state": "exited",
            "termination_confirmed": True,
            "launch_fenced": True,
            "artifacts": artifacts,
            **changes,
        },
    )


def test_source_delivery_is_atomic_across_authority_connections(tmp_path, config):
    path = tmp_path / "authority.db"
    Coordinator(path)

    def deliver(_):
        return enroll(Coordinator(path), config)["id"]

    with ThreadPoolExecutor(max_workers=8) as executor:
        identities = list(executor.map(deliver, range(16)))
    assert len(set(identities)) == 1
    store = Coordinator(path)
    tasks = store.snapshot()["task"]
    assert len(tasks) == 1
    assert tasks[0]["attempts"] == tasks[0]["allocated_seconds"] == 0
    with pytest.raises(Conflict, match="source retry"):
        enroll(
            store, config, requirements="Different input under same execution request"
        )
    rerun = enroll(store, config, request_key="explicit-new-run")
    assert rerun["id"] != tasks[0]["id"]


def test_lost_claim_reply_expiry_and_restart_keep_one_budget_and_binding(
    tmp_path, config
):
    clock = [100.0]
    path = tmp_path / "authority.db"
    store = Coordinator(path, clock=lambda: clock[0], boot_id="same-boot")
    task = enroll(store, config)
    first = claim(store, config, task["id"])
    assert first["launch_allowed"]
    assert first["attempt"]["state"] == "unknown"
    assert first["binding"]["base"] == BASE
    assert first["binding"]["runtime_principal"] == "trusted-runtime"
    assert first["binding"]["attempt_id"] == first["attempt"]["id"]
    with pytest.raises(Conflict):
        store.authorize_launch(first["attempt"]["id"], first["attempt"]["worker"])
    with pytest.raises(Conflict):
        store.start_attempt(task["id"], "local-worker", ["python"], 60, "another")
    clock[0] += 80
    reopened = Coordinator(path, clock=lambda: clock[0], boot_id="same-boot")
    retry = claim(reopened, config, task["id"])
    assert retry["binding"] == first["binding"]
    assert not retry["launch_allowed"]
    assert retry["remaining_seconds"] == 0
    assert reopened.snapshot()["task"][0]["attempts"] == 1
    assert reopened.snapshot()["task"][0]["allocated_seconds"] == 60
    with pytest.raises(Conflict):
        claim(reopened, config, task["id"], base="c" * 40)
    with pytest.raises(Conflict):
        claim(reopened, config, task["id"], worker_id="replacement", request_key="new")


def test_worker_cannot_allocate_two_unresolved_roots(tmp_path, config):
    store = Coordinator(tmp_path / "authority.db")
    first = enroll(store, config)
    second = enroll(store, config, source="github:issue:20")
    claim(store, config, first["id"])
    with pytest.raises(Conflict, match="worker incarnation"):
        claim(store, config, second["id"], request_key="different-task")
    assert claim(store, config, second["id"], worker_id="another-worker")[
        "launch_allowed"
    ]


def test_lost_claim_is_recoverable_after_profile_revision_or_removal(tmp_path, config):
    store = Coordinator(tmp_path / "authority.db")
    task = enroll(store, config)
    first = claim(store, config, task["id"])
    changed = copy.deepcopy(config)
    changed["repositories"][REPOSITORY]["profiles"]["approved"].update(
        base="c" * 40, attempt_seconds=30
    )
    recovered = claim(store, changed, task["id"])
    assert recovered["binding"] == first["binding"]
    assert recovered["requirements"] == first["requirements"]
    assert recovered["launch_allowed"] is False
    removed = claim(store, config, task["id"], profile_spec=None)
    assert removed["binding"] == first["binding"]
    assert removed["launch_allowed"] is False
    assert store.snapshot()["task"][0]["attempts"] == 1
    assert store.snapshot()["task"][0]["allocated_seconds"] == 60
    with pytest.raises(Conflict, match="retry key"):
        claim(store, config, task["id"], base="c" * 40)


def test_terminal_requires_hash_verified_capture_and_original_runtime(tmp_path, config):
    store = Coordinator(tmp_path / "authority.db")
    attempt = claim(store, config, enroll(store, config)["id"])["attempt"]
    aid = attempt["id"]
    with pytest.raises(Conflict):
        terminal(store, aid, {})
    with pytest.raises(Conflict):
        store.observe(aid, "exited", True)
    with pytest.raises(Conflict):
        store.managed_capture(
            **SCOPE,
            runtime_principal="forged",
            attempt_id=aid,
            kind="patch",
            content="x",
        )
    artifacts = capture(store, aid)
    assert capture(store, aid) == artifacts
    with pytest.raises(Conflict, match="different content"):
        store.managed_capture(
            **SCOPE,
            runtime_principal="trusted-runtime",
            attempt_id=aid,
            kind="patch",
            content="replacement",
        )
    with pytest.raises(Conflict):
        terminal(store, aid, artifacts, launch_fenced=False)
    with store.connect() as db:
        original = db.execute(
            "SELECT content FROM artifacts WHERE id=?", (artifacts["log"],)
        ).fetchone()[0]
        db.execute(
            "UPDATE artifacts SET content=? WHERE id=?",
            (b"corruption", artifacts["log"]),
        )
    with pytest.raises(Conflict, match="verification failed"):
        terminal(store, aid, artifacts)
    assert not store.snapshot()["attempt"][0]["termination_confirmed"]
    with store.connect() as db:
        db.execute(
            "UPDATE artifacts SET content=? WHERE id=?", (original, artifacts["log"])
        )
    final = terminal(store, aid, artifacts)
    assert final["termination_confirmed"] and final["launch_fenced"]
    assert terminal(Coordinator(store.path), aid, artifacts) == final
    with pytest.raises(Conflict, match="receipt changed"):
        terminal(store, aid, artifacts, state="timed_out")


def test_revoked_permission_still_allows_salvage_not_fresh_launch(tmp_path, config):
    store = Coordinator(tmp_path / "authority.db")
    task = enroll(store, config)
    initial = claim(store, config, task["id"])
    aid = initial["attempt"]["id"]
    store.request_cancel(aid, initial["attempt"]["worker"])
    profiles = config["repositories"][REPOSITORY]["profiles"]
    denied = store.managed_permission(
        **SCOPE, runtime_principal="trusted-runtime", attempt_id=aid, profiles=profiles
    )
    assert not denied["launch_allowed"]
    running = store.managed_observe(
        **SCOPE,
        runtime_principal="trusted-runtime",
        attempt_id=aid,
        state="running",
        termination_confirmed=False,
        launch_fenced=False,
        artifacts={},
    )
    assert running["state"] == "cancel_requested"
    terminal(store, aid, capture(store, aid))
    retry = claim(store, config, task["id"])
    assert retry["binding"] == initial["binding"] and not retry["launch_allowed"]


def test_profile_change_and_reboot_revoke_but_do_not_replace_binding(tmp_path, config):
    path = tmp_path / "authority.db"
    store = Coordinator(path, boot_id="boot-one")
    aid = claim(store, config, enroll(store, config)["id"])["attempt"]["id"]
    profile = copy.deepcopy(config["repositories"][REPOSITORY]["profiles"])
    profile["approved"]["base"] = "c" * 40
    denied = store.managed_permission(
        **SCOPE, runtime_principal="trusted-runtime", attempt_id=aid, profiles=profile
    )
    assert not denied["launch_allowed"] and "profile" in denied["reason"]
    reopened = Coordinator(path, boot_id="boot-two")
    result = reopened.managed_permission(
        **SCOPE,
        runtime_principal="trusted-runtime",
        attempt_id=aid,
        profiles=config["repositories"][REPOSITORY]["profiles"],
    )
    assert not result["launch_allowed"]
    assert not result["attempt"]["termination_confirmed"]


def test_requirements_revision_keeps_original_input_for_recovery(tmp_path, config):
    store = Coordinator(tmp_path / "authority.db")
    task = enroll(store, config)
    initial = claim(store, config, task["id"])
    aid = initial["attempt"]["id"]
    store.revise(
        task["id"], 1, "New owner requirements", ["tests"], ["independent-review"]
    )
    recovered = claim(store, config, task["id"])
    assert recovered["binding"] == initial["binding"]
    assert recovered["requirements"] == initial["requirements"]
    assert not recovered["launch_allowed"]
    permission = store.managed_permission(
        **SCOPE,
        runtime_principal="trusted-runtime",
        attempt_id=aid,
        profiles=config["repositories"][REPOSITORY]["profiles"],
    )
    assert permission["requirements"] == initial["requirements"]
    artifacts = capture(store, aid)
    assert terminal(store, aid, artifacts)["termination_confirmed"]
    with pytest.raises(Conflict, match="requirements changed"):
        store.managed_candidate(
            **SCOPE,
            runtime_principal="trusted-runtime",
            attempt_id=aid,
            artifact_id=artifacts["patch"],
        )


@pytest.mark.asyncio
async def test_real_http_scope_roles_capture_and_independent_review(
    tmp_path, config, credentials
):
    store = Coordinator(tmp_path / "authority.db")
    legacy = store.enroll("local", "legacy requirements", ["test"])
    foreign = enroll(
        store, config, repository=OTHER, requirements="private other repository"
    )
    async with TestClient(
        TestServer(create_app(store, credentials, managed=config))
    ) as client:

        async def send(role, path, payload, expected=200):
            response = await client.post(
                path, json=payload, headers={"Authorization": "Bearer " + TOKENS[role]}
            )
            text = await response.text()
            assert response.status == expected, text
            return (
                json.loads(text)
                if response.content_type == "application/json"
                else text
            )

        task = (await send("ingress", "/managed/enroll", source_payload()))["task"]
        duplicate = await send("ingress", "/managed/enroll", source_payload())
        assert duplicate["task"]["id"] == task["id"]
        await send(
            "ingress", "/managed/enroll", source_payload(requirements="changed"), 409
        )
        await send("ingress", "/managed/enroll", source_payload(repository=OTHER), 403)
        await send(
            "ingress", "/managed/enroll", source_payload(checks=["accept-me"]), 400
        )
        await send("ingress", "/call/enroll", {}, 403)
        await send(
            "worker",
            "/call/start_attempt",
            {
                "task_id": task["id"],
                "capabilities": ["python"],
                "seconds": 60,
                "request_key": "bypass",
            },
            403,
        )
        payload = {
            "schema_version": 1,
            **SCOPE,
            "task_id": task["id"],
            "profile": "approved",
            "worker_id": "worker-one",
            "request_key": "claim-one",
            "base": BASE,
        }
        result = await send("runtime", "/managed/claim", payload)
        aid = result["attempt"]["id"]
        await send(
            "runtime", "/managed/claim", payload | {"task_id": foreign["id"]}, 409
        )
        await send(
            "runtime",
            "/call/observe",
            {"attempt_id": aid, "state": "exited", "termination_confirmed": True},
            403,
        )
        await send(
            "owner",
            "/call/observe",
            {"attempt_id": aid, "state": "exited", "termination_confirmed": True},
            409,
        )
        await send(
            "worker",
            "/call/save_work",
            {"attempt_id": aid, "content": "fake-capture"},
            403,
        )
        hashes = {}
        for kind, content in {
            "patch": "diff --git a/test.py b/test.py\n",
            "log": "guest test result",
            "manifest": '{"archive_sha256":"' + "f" * 64 + '"}',
        }.items():
            captured = await send(
                "runtime",
                "/managed/capture",
                {
                    "schema_version": 1,
                    **SCOPE,
                    "attempt_id": aid,
                    "kind": kind,
                    "content": content,
                },
            )
            hashes[kind] = captured["artifact_id"]
        receipt = {
            "schema_version": 1,
            **SCOPE,
            "attempt_id": aid,
            "state": "exited",
            "termination_confirmed": True,
            "launch_fenced": True,
            "artifacts": hashes,
        }
        await send("foreign", "/managed/observe", receipt, 403)
        await send("runtime", "/managed/observe", receipt)
        candidate = (
            await send(
                "runtime",
                "/managed/candidate",
                {
                    "schema_version": 1,
                    **SCOPE,
                    "attempt_id": aid,
                    "artifact_id": hashes["patch"],
                },
            )
        )["candidate"]
        evidence = {
            "candidate_id": candidate["id"],
            "check": "tests",
            "passed": True,
            "input_revision": 1,
        }
        await send("self-review", "/call/evidence", evidence, 409)
        await send("reviewer", "/call/evidence", evidence)
        accepted = await send(
            "owner", "/call/accept", {"candidate_id": candidate["id"]}
        )
        assert accepted["result"]["release_authorized"] is False
        query = "?deployment_id=" + SCOPE["deployment_id"] + "&repository=" + REPOSITORY
        response = await client.get(
            "/managed/snapshot" + query,
            headers={"Authorization": "Bearer " + TOKENS["runtime"]},
        )
        snapshot = await response.json()
        assert [row["id"] for row in snapshot["task"]] == [task["id"]]
        assert snapshot["task"][0]["status"] == "accepted"
        assert snapshot["attempt"][0]["captured_artifacts"] == hashes
        response = await client.get(
            "/managed/artifacts/" + hashes["patch"] + query,
            headers={"Authorization": "Bearer " + TOKENS["reviewer"]},
        )
        assert await response.text() == "diff --git a/test.py b/test.py\n"
        response = await client.get(
            "/snapshot", headers={"Authorization": "Bearer " + TOKENS["worker"]}
        )
        assert [row["id"] for row in (await response.json())["task"]] == [legacy["id"]]
        response = await client.get(
            "/artifacts/" + hashes["patch"],
            headers={"Authorization": "Bearer " + TOKENS["worker"]},
        )
        assert response.status == 409
        response = await client.get(
            "/managed/capabilities" + query + "&profile=approved",
            headers={"Authorization": "Bearer " + TOKENS["runtime"]},
        )
        capabilities = await response.json()
        assert capabilities["base"] == BASE and capabilities["children"] is False
        assert (
            capabilities["external_root"] and len(capabilities["profile_digest"]) == 64
        )
        response = await client.get(
            "/snapshot", headers={"Authorization": "Bearer " + TOKENS["runtime"]}
        )
        assert response.status == 403


@pytest.mark.asyncio
async def test_missing_policy_invalid_schema_and_unauthenticated_requests(
    tmp_path, config, credentials
):
    store = Coordinator(tmp_path / "authority.db")
    async with TestClient(TestServer(create_app(store, credentials))) as client:
        response = await client.post(
            "/managed/enroll",
            json=source_payload(),
            headers={"Authorization": "Bearer " + TOKENS["ingress"]},
        )
        assert response.status == 503
    async with TestClient(
        TestServer(create_app(store, credentials, managed=config))
    ) as client:
        response = await client.post("/managed/enroll", json=source_payload())
        assert response.status == 401
        response = await client.post(
            "/managed/enroll",
            json=source_payload(schema_version=True),
            headers={"Authorization": "Bearer " + TOKENS["ingress"]},
        )
        assert response.status == 400
        assert store.snapshot()["task"] == []
    broken = copy.deepcopy(config)
    broken["repositories"][REPOSITORY]["profiles"]["approved"]["command"] = ["forged"]
    with pytest.raises(ValueError):
        create_app(store, credentials, managed=broken)
    broken_credentials = copy.deepcopy(credentials)
    broken_credentials[TOKENS["runtime"]].pop("repositories")
    with pytest.raises(ValueError):
        create_app(store, broken_credentials, managed=config)


@pytest.mark.asyncio
async def test_ingress_client_uses_actual_scoped_receipt(tmp_path, config, credentials):
    store = Coordinator(tmp_path / "authority.db")
    async with TestServer(create_app(store, credentials, managed=config)) as server:
        url = str(server.make_url("/")).rstrip("/")
        result = await submit(url, TOKENS["ingress"], source_payload())
        replay = await submit(url, TOKENS["ingress"], source_payload())
        assert result["task"]["id"] == replay["task"]["id"]
        with pytest.raises(ValueError, match="HTTP 403"):
            await submit(url, TOKENS["runtime"], source_payload())
    for url in (
        "http://remote.example",
        "https://token@remote.example",
        "https://remote.example/?token=secret",
        "file:///tmp/authority",
    ):
        with pytest.raises(ValueError):
            service_url(url)
