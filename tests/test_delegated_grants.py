"""Atomic delegated grant admission, scoped recovery and root capture barriers."""

from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json

from aiohttp.test_utils import TestClient, TestServer
import pytest

from src.core.collaboration.authority import Coordinator, Conflict, digest
from src.core.collaboration.delegated_grants import DelegatedGrantNotAllocated
from src.liminal_bridge.coordinator_service import create_app
from src.liminal_bridge.managed_service import validate_managed_config

REPOSITORY = "github:github.com/example/project"
SCOPE = {"deployment_id": "grant-test", "repository": REPOSITORY}
BASE = "a" * 40


@pytest.fixture
def config():
    return {
        "schema_version": 1,
        "deployment_id": SCOPE["deployment_id"],
        "repositories": {
            REPOSITORY: {
                "checks": ["tests"],
                "reviewers": ["reviewer"],
                "max_attempts": 3,
                "budget_seconds": 300,
                "profiles": {
                    "approved": {
                        "base": BASE,
                        "attempt_seconds": 60,
                        "capabilities": ["python", "tests"],
                        "max_delegated_grants": 2,
                        "max_grant_seconds": 30,
                        "max_grant_turns": 3,
                        "grant_capabilities": ["python"],
                    }
                },
            }
        },
    }


def profiles(config):
    return config["repositories"][REPOSITORY]["profiles"]


def root_attempt(store, config, key="one"):
    policy = config["repositories"][REPOSITORY]
    task = store.managed_enroll(
        **SCOPE,
        source="issue:" + key,
        request_key="run-one",
        title="Bounded work",
        requirements="Root requirements",
        policy=policy,
    )
    root = store.managed_claim(
        **SCOPE,
        runtime_principal="runtime",
        worker_id="worker:" + key,
        profile="approved",
        profile_spec=profiles(config)["approved"],
        task_id=task["id"],
        request_key="claim-one",
        base=BASE,
    )["attempt"]
    return task, root


def grant(store, config, root, key="grant-one", **changes):
    return store.managed_delegated_grant(
        **SCOPE,
        runtime_principal="runtime",
        attempt_id=root["id"],
        profiles=profiles(config),
        **{
            "request_key": key,
            "instructions": "Private grant instructions " + key,
            "seconds": 20,
            "max_turns": 2,
            "capabilities": ["python"],
            **changes,
        },
    )


def capture_grant(store, root, did):
    hashes = {}
    for kind, content in {
        "patch": "grant patch " + did,
        "log": "grant log " + did,
        "manifest": json.dumps({"delegation": did}),
    }.items():
        result = store.managed_delegation_capture(
            **SCOPE,
            runtime_principal="runtime",
            attempt_id=root["id"],
            delegation_id=did,
            kind=kind,
            content=content,
        )
        hashes[kind] = result["artifact_id"]
    return hashes


def end_grant(store, root, did, hashes, **changes):
    return store.managed_delegation_observe(
        **SCOPE,
        runtime_principal="runtime",
        attempt_id=root["id"],
        delegation_id=did,
        **{
            "state": "exited",
            "termination_confirmed": True,
            "launch_fenced": True,
            "artifacts": hashes,
            **changes,
        },
    )


def capture_root(store, root):
    return {
        kind: store.managed_capture(
            **SCOPE,
            runtime_principal="runtime",
            attempt_id=root["id"],
            kind=kind,
            content=content,
        )["artifact_id"]
        for kind, content in {
            "patch": "root patch",
            "log": "root log",
            "manifest": "{}",
        }.items()
    }


def end_root(store, root, hashes):
    return store.managed_observe(
        **SCOPE,
        runtime_principal="runtime",
        attempt_id=root["id"],
        state="exited",
        termination_confirmed=True,
        launch_fenced=True,
        artifacts=hashes,
    )


@pytest.mark.parametrize("limit,budget,expected", [(2, 300, 2), (4, 90, 1)])
def test_concurrent_delegations_share_one_task_allowance(
    tmp_path, config, limit, budget, expected
):
    policy = config["repositories"][REPOSITORY]
    policy["budget_seconds"] = budget
    policy["profiles"]["approved"]["max_delegated_grants"] = limit
    path = tmp_path / "authority.db"
    store = Coordinator(path, clock=lambda: 100, boot_id="boot")
    task, root = root_attempt(store, config)

    def allocate(number):
        try:
            return grant(
                Coordinator(path, clock=lambda: 100, boot_id="boot"),
                config,
                root,
                str(number),
            )["binding"]["delegation_id"]
        except DelegatedGrantNotAllocated:
            return None

    with ThreadPoolExecutor(max_workers=8) as executor:
        allocated = list(executor.map(allocate, range(12)))
    identities = {value for value in allocated if value is not None}
    assert len(identities) == expected
    snapshot = store.snapshot()
    assert len(snapshot["task"]) == len(snapshot["attempt"]) == 1
    assert snapshot["task"][0]["allocated_seconds"] == 60 + 20 * expected
    assert snapshot["task"][0]["attempts"] == 1
    for did in identities:
        end_grant(store, root, did, capture_grant(store, root, did))
    with pytest.raises(DelegatedGrantNotAllocated):
        grant(store, config, root, "no-refund")
    assert store.snapshot()["task"][0]["allocated_seconds"] == 60 + 20 * expected


def test_grant_and_turn_retries_survive_restart_revocation_and_profile_removal(
    tmp_path, config
):
    path = tmp_path / "authority.db"
    store = Coordinator(path, clock=lambda: 100, boot_id="boot")
    task, root = root_attempt(store, config)
    first = grant(store, config, root)
    did = first["binding"]["delegation_id"]
    args = dict(
        SCOPE,
        runtime_principal="runtime",
        attempt_id=root["id"],
        delegation_id=did,
    )
    turn = store.managed_delegated_turn(
        **args,
        request_key="model-one",
        request_digest="a" * 64,
        profiles=profiles(config),
    )
    assert turn["turn"]["number"] == 1
    with pytest.raises(Conflict, match="turn retry payload"):
        store.managed_delegated_turn(
            **args,
            request_key="model-one",
            request_digest="b" * 64,
            profiles=profiles(config),
        )
    store.managed_delegation_control(
        **SCOPE,
        runtime_principal="runtime",
        attempt_id=root["id"],
        action="cancel",
        reason="owner cancellation",
    )
    reopened = Coordinator(path, clock=lambda: 100, boot_id="boot")
    removed = copy.deepcopy(config)
    removed["repositories"][REPOSITORY]["profiles"] = {}
    recovered = grant(reopened, removed, root)
    assert recovered["binding"] == first["binding"]
    assert recovered["instructions"] == first["instructions"]
    assert not recovered["launch_allowed"]
    retried_turn = reopened.managed_delegated_turn(
        **args, request_key="model-one", request_digest="a" * 64, profiles={}
    )
    assert retried_turn["turn"] == turn["turn"] and not retried_turn["launch_allowed"]
    assert retried_turn["delegation"]["turns_allocated"] == 1
    assert reopened.snapshot()["task"][0]["allocated_seconds"] == 80
    with pytest.raises(Conflict, match="delegation retry"):
        grant(reopened, removed, root, instructions="Changed request")
    with pytest.raises(DelegatedGrantNotAllocated):
        grant(reopened, removed, root, "new request")
    with pytest.raises(Conflict):
        reopened.managed_delegated_turn(
            **args, request_key="new-turn", request_digest="c" * 64, profiles={}
        )
    end_grant(reopened, root, did, capture_grant(reopened, root, did))


def test_deadline_revision_and_reboot_never_extend_grant_permission(tmp_path, config):
    now = [100]
    profile = profiles(config)["approved"]
    profile["max_grant_seconds"] = 60
    store = Coordinator(tmp_path / "authority.db", clock=lambda: now[0], boot_id="one")
    task, root = root_attempt(store, config)
    now[0] = 150
    granted = grant(store, config, root, seconds=60)
    did = granted["binding"]["delegation_id"]
    assert granted["binding"]["deadline"] == root["deadline"] == 160
    assert granted["remaining_seconds"] == 10
    assert store.snapshot()["task"][0]["allocated_seconds"] == 120
    store.revise(task["id"], 1, "new requirements", ["tests"], ["reviewer"])
    assert not grant(store, config, root, seconds=60)["launch_allowed"]
    assert grant(store, config, root, seconds=60)["binding"] == granted["binding"]
    reopened = Coordinator(store.path, clock=lambda: now[0], boot_id="two")
    permission = reopened.managed_delegated_permission(
        **SCOPE,
        runtime_principal="runtime",
        attempt_id=root["id"],
        delegation_id=did,
        profiles=profiles(config),
    )
    assert (
        not permission["launch_allowed"]
        and not permission["delegation"]["termination_confirmed"]
    )
    end_grant(reopened, root, did, capture_grant(reopened, root, did))


def test_turn_limit_drain_and_capability_narrowing(tmp_path, config):
    store = Coordinator(tmp_path / "authority.db")
    _, root = root_attempt(store, config)
    for changes in ({"capabilities": ["owner"]}, {"max_turns": 4}, {"seconds": 31}):
        with pytest.raises(DelegatedGrantNotAllocated):
            grant(store, config, root, **changes)
    granted = grant(store, config, root)
    did = granted["binding"]["delegation_id"]
    args = dict(
        SCOPE,
        runtime_principal="runtime",
        attempt_id=root["id"],
        delegation_id=did,
        profiles=profiles(config),
    )
    for number in range(2):
        turn = store.managed_delegated_turn(
            **args, request_key=str(number), request_digest="a" * 64
        )
        assert turn["turn"]["number"] == number + 1
    with pytest.raises(Conflict, match="turn allowance"):
        store.managed_delegated_turn(
            **args, request_key="third", request_digest="a" * 64
        )
    store.managed_delegation_control(
        **SCOPE,
        runtime_principal="runtime",
        attempt_id=root["id"],
        action="close",
        reason="worker draining",
    )
    assert store.managed_delegated_permission(**args)["launch_allowed"]
    with pytest.raises(DelegatedGrantNotAllocated, match="admission is closed"):
        grant(store, config, root, "after drain")
    with pytest.raises(Conflict):
        store.managed_delegated_grant(
            **SCOPE,
            runtime_principal="runtime",
            attempt_id=did,
            profiles=profiles(config),
            request_key="grandgrant",
            instructions="recursive",
            seconds=1,
            max_turns=1,
            capabilities=[],
        )


def test_grant_expiry_uses_monotonic_time_without_refund(tmp_path, config):
    wall, monotonic = [100], [100]
    store = Coordinator(
        tmp_path / "authority.db",
        clock=lambda: wall[0],
        monotonic_clock=lambda: monotonic[0],
        boot_id="same-boot",
    )
    _, root = root_attempt(store, config)
    granted = grant(store, config, root, seconds=5)
    did = granted["binding"]["delegation_id"]
    args = dict(
        SCOPE,
        runtime_principal="runtime",
        attempt_id=root["id"],
        delegation_id=did,
        profiles=profiles(config),
    )
    turn = store.managed_delegated_turn(
        **args, request_key="one", request_digest="a" * 64
    )
    wall[0], monotonic[0] = 10, 106
    assert store.managed_permission(
        **SCOPE,
        runtime_principal="runtime",
        attempt_id=root["id"],
        profiles=profiles(config),
    )["launch_allowed"]
    denied = store.managed_delegated_permission(**args)
    assert not denied["launch_allowed"] and denied["remaining_seconds"] == 0
    assert not grant(store, config, root, seconds=5)["launch_allowed"]
    replay = store.managed_delegated_turn(
        **args, request_key="one", request_digest="a" * 64
    )
    assert replay["turn"] == turn["turn"] and not replay["launch_allowed"]
    assert store.snapshot()["task"][0]["allocated_seconds"] == 65
    end_grant(store, root, did, capture_grant(store, root, did))


def test_root_waits_for_every_verified_delegation_and_binds_candidate_lineage(
    tmp_path, config
):
    store = Coordinator(tmp_path / "authority.db")
    _, root = root_attempt(store, config)
    first = grant(store, config, root)["binding"]["delegation_id"]
    second = grant(store, config, root, "second")["binding"]["delegation_id"]
    root_hashes = capture_root(store, root)
    with pytest.raises(Conflict, match="unresolved delegation"):
        end_root(store, root, root_hashes)
    hashes = capture_grant(store, root, first)
    with pytest.raises(Conflict):
        end_grant(store, root, first, hashes, launch_fenced=False)
    end_grant(store, root, first, hashes)
    with pytest.raises(Conflict):
        end_root(store, root, root_hashes)
    second_hashes = capture_grant(store, root, second)
    end_grant(store, root, second, second_hashes)
    with store.connect() as db:
        original = db.execute(
            "SELECT content FROM artifacts WHERE id=?", (hashes["log"],)
        ).fetchone()[0]
        db.execute(
            "UPDATE artifacts SET content=? WHERE id=?", (b"corrupted", hashes["log"])
        )
    with pytest.raises(Conflict, match="capture verification"):
        end_root(store, root, root_hashes)
    assert not store.snapshot()["attempt"][0]["termination_confirmed"]
    with store.connect() as db:
        db.execute(
            "UPDATE artifacts SET content=? WHERE id=?", (original, hashes["log"])
        )
    final = end_root(store, root, root_hashes)
    assert {row["delegation_id"] for row in final["delegation_lineage"]} == {
        first,
        second,
    }
    candidate = store.managed_candidate(
        **SCOPE,
        runtime_principal="runtime",
        attempt_id=root["id"],
        artifact_id=root_hashes["patch"],
    )
    assert candidate["delegation_lineage"] == final["delegation_lineage"]
    assert len(store.snapshot()["task"]) == 1
    with pytest.raises(Conflict):
        store.managed_delegation_artifact(
            **SCOPE,
            runtime_principal="runtime",
            attempt_id=root["id"],
            delegation_id=second,
            artifact_id=hashes["patch"],
        )
    with pytest.raises(Conflict):
        store.scoped_artifact(hashes["patch"], SCOPE)


def test_old_profile_digest_and_invalid_policy_are_fail_closed(config):
    old = copy.deepcopy(config)
    profile = profiles(old)["approved"]
    for field in (
        "max_delegated_grants",
        "max_grant_seconds",
        "max_grant_turns",
        "grant_capabilities",
    ):
        profile.pop(field)
    expected = digest(profile)
    validated = validate_managed_config(old)
    assert validated == old and digest(profiles(validated)["approved"]) == expected
    for changes in (
        {"max_delegated_grants": True},
        {"max_delegated_grants": 65},
        {"grant_capabilities": ["owner"]},
        {"max_grant_turns": 0},
        {"max_grant_seconds": 61},
    ):
        invalid = copy.deepcopy(config)
        profiles(invalid)["approved"].update(changes)
        with pytest.raises(ValueError):
            validate_managed_config(invalid)


@pytest.mark.asyncio
async def test_http_rooted_reads_controls_and_unforgeable_service_roles(
    tmp_path, config
):
    store = Coordinator(tmp_path / "authority.db")
    _, root = root_attempt(store, config)
    _, other_root = root_attempt(store, config, "other")
    credentials = {
        "r"
        * 40: {
            "identity": "runtime",
            "role": "runtime",
            "deployment_id": SCOPE["deployment_id"],
            "repositories": [REPOSITORY],
        },
        "f"
        * 40: {
            "identity": "foreign",
            "role": "runtime",
            "deployment_id": SCOPE["deployment_id"],
            "repositories": [REPOSITORY],
        },
        "o" * 40: {"identity": "owner", "role": "owner"},
        "i"
        * 40: {
            "identity": "ingress",
            "role": "ingress",
            "deployment_id": SCOPE["deployment_id"],
            "repositories": [REPOSITORY],
        },
    }
    async with TestClient(
        TestServer(create_app(store, credentials, managed=config))
    ) as client:

        async def post(path, payload, status=200, token="r"):
            response = await client.post(
                path,
                json={
                    "schema_version": 1,
                    **SCOPE,
                    "attempt_id": root["id"],
                    **payload,
                },
                headers={"Authorization": "Bearer " + token * 40},
            )
            text = await response.text()
            assert response.status == status, text
            return (
                json.loads(text)
                if response.content_type == "application/json"
                else text
            )

        request = {
            "request_key": "one",
            "instructions": "Private HTTP grant",
            "seconds": 20,
            "max_turns": 2,
            "capabilities": ["python"],
        }
        result = await post("/managed/delegations/grant", request)
        did = result["binding"]["delegation_id"]
        await post(
            "/managed/delegations/grant",
            request | {"runtime_principal": "forged"},
            400,
        )
        await post("/managed/delegations/grant", request, 403, "i")
        await post("/managed/delegations/grant", request, 409, "f")
        await post(
            "/managed/delegations/permission",
            {"delegation_id": did, "attempt_id": other_root["id"]},
            409,
        )
        await post(
            "/managed/delegations/revoke",
            {
                "delegation_id": did,
                "attempt_id": other_root["id"],
                "reason": "sibling attack",
            },
            409,
        )
        query = "?deployment_id=" + SCOPE["deployment_id"] + "&repository=" + REPOSITORY
        headers = {"Authorization": "Bearer " + "r" * 40}
        response = await client.get(
            "/managed/delegations/" + did + query + "&attempt_id=" + root["id"],
            headers=headers,
        )
        assert response.status == 200
        assert (await response.json())["delegations"][0][
            "instructions"
        ] == "Private HTTP grant"
        response = await client.get(
            "/managed/delegations/" + did + query + "&attempt_id=" + other_root["id"],
            headers=headers,
        )
        assert response.status == 409
        response = await client.get(
            "/managed/delegations" + query + "&attempt_id=" + root["id"],
            headers={"Authorization": "Bearer " + "i" * 40},
        )
        assert response.status == 403
        response = await client.get("/managed/snapshot" + query, headers=headers)
        assert "Private HTTP grant" not in await response.text()
        response = await client.get(
            "/managed/capabilities" + query + "&profile=approved", headers=headers
        )
        cap = await response.json()
        assert cap["children"] is False and cap["delegated_grants"] is True
        await post("/managed/cancel", {"reason": "owner stop"}, token="o")
        untouched = next(
            row for row in store.snapshot()["attempt"] if row["id"] == other_root["id"]
        )
        assert untouched["state"] == "unknown" and not untouched.get("cancel_requested")
        denied = await post(
            "/managed/delegations/grant", request | {"request_key": "later"}, 409
        )
        assert denied["code"] == "delegated_grant_not_allocated"
        recovered = await post("/managed/delegations/grant", request)
        assert (
            recovered["binding"] == result["binding"]
            and not recovered["launch_allowed"]
        )
