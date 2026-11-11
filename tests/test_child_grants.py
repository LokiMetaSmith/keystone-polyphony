"""Atomic child admission, scoped recovery and root capture barriers."""

from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json

from aiohttp.test_utils import TestClient, TestServer
import pytest

from src.core.collaboration.authority import Coordinator, Conflict, digest
from src.core.collaboration.child_grants import ChildNotAllocated
from src.liminal_bridge.coordinator_service import create_app
from src.liminal_bridge.managed_service import validate_managed_config

REPOSITORY = "github:github.com/example/project"
SCOPE = {"deployment_id": "child-test", "repository": REPOSITORY}
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
                        "max_children": 2,
                        "max_child_seconds": 30,
                        "max_child_turns": 3,
                        "child_capabilities": ["python"],
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


def child(store, config, root, key="child-one", **changes):
    return store.managed_child_grant(
        **SCOPE,
        runtime_principal="runtime",
        attempt_id=root["id"],
        profiles=profiles(config),
        **{
            "request_key": key,
            "instructions": "Private child instructions " + key,
            "seconds": 20,
            "max_turns": 2,
            "capabilities": ["python"],
            **changes,
        },
    )


def capture_child(store, root, cid):
    hashes = {}
    for kind, content in {
        "patch": "child patch " + cid,
        "log": "child log " + cid,
        "manifest": json.dumps({"child": cid}),
    }.items():
        result = store.managed_child_capture(
            **SCOPE,
            runtime_principal="runtime",
            attempt_id=root["id"],
            child_id=cid,
            kind=kind,
            content=content,
        )
        hashes[kind] = result["artifact_id"]
    return hashes


def end_child(store, root, cid, hashes, **changes):
    return store.managed_child_observe(
        **SCOPE,
        runtime_principal="runtime",
        attempt_id=root["id"],
        child_id=cid,
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
def test_concurrent_children_share_one_task_allowance(
    tmp_path, config, limit, budget, expected
):
    policy = config["repositories"][REPOSITORY]
    policy["budget_seconds"] = budget
    policy["profiles"]["approved"]["max_children"] = limit
    path = tmp_path / "authority.db"
    store = Coordinator(path, clock=lambda: 100, boot_id="boot")
    task, root = root_attempt(store, config)

    def allocate(number):
        try:
            return child(
                Coordinator(path, clock=lambda: 100, boot_id="boot"),
                config,
                root,
                str(number),
            )["binding"]["child_id"]
        except ChildNotAllocated:
            return None

    with ThreadPoolExecutor(max_workers=8) as executor:
        allocated = list(executor.map(allocate, range(12)))
    identities = {value for value in allocated if value is not None}
    assert len(identities) == expected
    snapshot = store.snapshot()
    assert len(snapshot["task"]) == len(snapshot["attempt"]) == 1
    assert snapshot["task"][0]["allocated_seconds"] == 60 + 20 * expected
    assert snapshot["task"][0]["attempts"] == 1
    for cid in identities:
        end_child(store, root, cid, capture_child(store, root, cid))
    with pytest.raises(ChildNotAllocated):
        child(store, config, root, "no-refund")
    assert store.snapshot()["task"][0]["allocated_seconds"] == 60 + 20 * expected


def test_grant_and_turn_retries_survive_restart_revocation_and_profile_removal(
    tmp_path, config
):
    path = tmp_path / "authority.db"
    store = Coordinator(path, clock=lambda: 100, boot_id="boot")
    task, root = root_attempt(store, config)
    first = child(store, config, root)
    cid = first["binding"]["child_id"]
    args = dict(SCOPE, runtime_principal="runtime", attempt_id=root["id"], child_id=cid)
    turn = store.managed_child_turn(
        **args,
        request_key="model-one",
        request_digest="a" * 64,
        profiles=profiles(config),
    )
    assert turn["turn"]["number"] == 1
    with pytest.raises(Conflict, match="turn retry payload"):
        store.managed_child_turn(
            **args,
            request_key="model-one",
            request_digest="b" * 64,
            profiles=profiles(config),
        )
    store.managed_child_control(
        **SCOPE,
        runtime_principal="runtime",
        attempt_id=root["id"],
        action="cancel",
        reason="owner cancellation",
    )
    reopened = Coordinator(path, clock=lambda: 100, boot_id="boot")
    removed = copy.deepcopy(config)
    removed["repositories"][REPOSITORY]["profiles"] = {}
    recovered = child(reopened, removed, root)
    assert recovered["binding"] == first["binding"]
    assert recovered["instructions"] == first["instructions"]
    assert not recovered["launch_allowed"]
    retried_turn = reopened.managed_child_turn(
        **args, request_key="model-one", request_digest="a" * 64, profiles={}
    )
    assert retried_turn["turn"] == turn["turn"] and not retried_turn["launch_allowed"]
    assert retried_turn["child"]["turns_allocated"] == 1
    assert reopened.snapshot()["task"][0]["allocated_seconds"] == 80
    with pytest.raises(Conflict, match="child retry"):
        child(reopened, removed, root, instructions="Changed request")
    with pytest.raises(ChildNotAllocated):
        child(reopened, removed, root, "new request")
    with pytest.raises(Conflict):
        reopened.managed_child_turn(
            **args, request_key="new-turn", request_digest="c" * 64, profiles={}
        )
    end_child(reopened, root, cid, capture_child(reopened, root, cid))


def test_deadline_revision_and_reboot_never_extend_child_permission(tmp_path, config):
    now = [100]
    profile = profiles(config)["approved"]
    profile["max_child_seconds"] = 60
    store = Coordinator(tmp_path / "authority.db", clock=lambda: now[0], boot_id="one")
    task, root = root_attempt(store, config)
    now[0] = 150
    granted = child(store, config, root, seconds=60)
    cid = granted["binding"]["child_id"]
    assert granted["binding"]["deadline"] == root["deadline"] == 160
    assert granted["remaining_seconds"] == 10
    assert store.snapshot()["task"][0]["allocated_seconds"] == 120
    store.revise(task["id"], 1, "new requirements", ["tests"], ["reviewer"])
    assert not child(store, config, root, seconds=60)["launch_allowed"]
    assert child(store, config, root, seconds=60)["binding"] == granted["binding"]
    reopened = Coordinator(store.path, clock=lambda: now[0], boot_id="two")
    permission = reopened.managed_child_permission(
        **SCOPE,
        runtime_principal="runtime",
        attempt_id=root["id"],
        child_id=cid,
        profiles=profiles(config),
    )
    assert (
        not permission["launch_allowed"]
        and not permission["child"]["termination_confirmed"]
    )
    end_child(reopened, root, cid, capture_child(reopened, root, cid))


def test_turn_limit_drain_and_capability_narrowing(tmp_path, config):
    store = Coordinator(tmp_path / "authority.db")
    _, root = root_attempt(store, config)
    for changes in ({"capabilities": ["owner"]}, {"max_turns": 4}, {"seconds": 31}):
        with pytest.raises(ChildNotAllocated):
            child(store, config, root, **changes)
    granted = child(store, config, root)
    cid = granted["binding"]["child_id"]
    args = dict(
        SCOPE,
        runtime_principal="runtime",
        attempt_id=root["id"],
        child_id=cid,
        profiles=profiles(config),
    )
    for number in range(2):
        turn = store.managed_child_turn(
            **args, request_key=str(number), request_digest="a" * 64
        )
        assert turn["turn"]["number"] == number + 1
    with pytest.raises(Conflict, match="turn allowance"):
        store.managed_child_turn(**args, request_key="third", request_digest="a" * 64)
    store.managed_child_control(
        **SCOPE,
        runtime_principal="runtime",
        attempt_id=root["id"],
        action="close",
        reason="worker draining",
    )
    assert store.managed_child_permission(**args)["launch_allowed"]
    with pytest.raises(ChildNotAllocated, match="admission is closed"):
        child(store, config, root, "after drain")
    with pytest.raises(Conflict):
        store.managed_child_grant(
            **SCOPE,
            runtime_principal="runtime",
            attempt_id=cid,
            profiles=profiles(config),
            request_key="grandchild",
            instructions="recursive",
            seconds=1,
            max_turns=1,
            capabilities=[],
        )


def test_child_expiry_uses_monotonic_time_without_refund(tmp_path, config):
    wall, monotonic = [100], [100]
    store = Coordinator(
        tmp_path / "authority.db",
        clock=lambda: wall[0],
        monotonic_clock=lambda: monotonic[0],
        boot_id="same-boot",
    )
    _, root = root_attempt(store, config)
    granted = child(store, config, root, seconds=5)
    cid = granted["binding"]["child_id"]
    args = dict(
        SCOPE,
        runtime_principal="runtime",
        attempt_id=root["id"],
        child_id=cid,
        profiles=profiles(config),
    )
    turn = store.managed_child_turn(**args, request_key="one", request_digest="a" * 64)
    wall[0], monotonic[0] = 10, 106
    assert store.managed_permission(
        **SCOPE,
        runtime_principal="runtime",
        attempt_id=root["id"],
        profiles=profiles(config),
    )["launch_allowed"]
    denied = store.managed_child_permission(**args)
    assert not denied["launch_allowed"] and denied["remaining_seconds"] == 0
    assert not child(store, config, root, seconds=5)["launch_allowed"]
    replay = store.managed_child_turn(
        **args, request_key="one", request_digest="a" * 64
    )
    assert replay["turn"] == turn["turn"] and not replay["launch_allowed"]
    assert store.snapshot()["task"][0]["allocated_seconds"] == 65
    end_child(store, root, cid, capture_child(store, root, cid))


def test_root_waits_for_every_verified_child_and_binds_candidate_lineage(
    tmp_path, config
):
    store = Coordinator(tmp_path / "authority.db")
    _, root = root_attempt(store, config)
    first = child(store, config, root)["binding"]["child_id"]
    second = child(store, config, root, "second")["binding"]["child_id"]
    root_hashes = capture_root(store, root)
    with pytest.raises(Conflict, match="unresolved child"):
        end_root(store, root, root_hashes)
    hashes = capture_child(store, root, first)
    with pytest.raises(Conflict):
        end_child(store, root, first, hashes, launch_fenced=False)
    end_child(store, root, first, hashes)
    with pytest.raises(Conflict):
        end_root(store, root, root_hashes)
    second_hashes = capture_child(store, root, second)
    end_child(store, root, second, second_hashes)
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
    assert {row["child_id"] for row in final["child_lineage"]} == {first, second}
    candidate = store.managed_candidate(
        **SCOPE,
        runtime_principal="runtime",
        attempt_id=root["id"],
        artifact_id=root_hashes["patch"],
    )
    assert candidate["child_lineage"] == final["child_lineage"]
    assert len(store.snapshot()["task"]) == 1
    with pytest.raises(Conflict):
        store.managed_child_artifact(
            **SCOPE,
            runtime_principal="runtime",
            attempt_id=root["id"],
            child_id=second,
            artifact_id=hashes["patch"],
        )
    with pytest.raises(Conflict):
        store.scoped_artifact(hashes["patch"], SCOPE)


def test_old_profile_digest_and_invalid_policy_are_fail_closed(config):
    old = copy.deepcopy(config)
    profile = profiles(old)["approved"]
    for field in (
        "max_children",
        "max_child_seconds",
        "max_child_turns",
        "child_capabilities",
    ):
        profile.pop(field)
    expected = digest(profile)
    validated = validate_managed_config(old)
    assert validated == old and digest(profiles(validated)["approved"]) == expected
    for changes in (
        {"max_children": True},
        {"max_children": 65},
        {"child_capabilities": ["owner"]},
        {"max_child_turns": 0},
        {"max_child_seconds": 61},
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
            "instructions": "Private HTTP child",
            "seconds": 20,
            "max_turns": 2,
            "capabilities": ["python"],
        }
        result = await post("/managed/children/grant", request)
        cid = result["binding"]["child_id"]
        await post(
            "/managed/children/grant", request | {"runtime_principal": "forged"}, 400
        )
        await post("/managed/children/grant", request, 403, "i")
        await post("/managed/children/grant", request, 409, "f")
        await post(
            "/managed/children/permission",
            {"child_id": cid, "attempt_id": other_root["id"]},
            409,
        )
        await post(
            "/managed/children/revoke",
            {
                "child_id": cid,
                "attempt_id": other_root["id"],
                "reason": "sibling attack",
            },
            409,
        )
        query = "?deployment_id=" + SCOPE["deployment_id"] + "&repository=" + REPOSITORY
        headers = {"Authorization": "Bearer " + "r" * 40}
        response = await client.get(
            "/managed/children/" + cid + query + "&attempt_id=" + root["id"],
            headers=headers,
        )
        assert response.status == 200
        assert (await response.json())["children"][0][
            "instructions"
        ] == "Private HTTP child"
        response = await client.get(
            "/managed/children/" + cid + query + "&attempt_id=" + other_root["id"],
            headers=headers,
        )
        assert response.status == 409
        response = await client.get(
            "/managed/children" + query + "&attempt_id=" + root["id"],
            headers={"Authorization": "Bearer " + "i" * 40},
        )
        assert response.status == 403
        response = await client.get("/managed/snapshot" + query, headers=headers)
        assert "Private HTTP child" not in await response.text()
        response = await client.get(
            "/managed/capabilities" + query + "&profile=approved", headers=headers
        )
        cap = await response.json()
        assert cap["children"] is False and cap["child_grants"] is True
        await post("/managed/cancel", {"reason": "owner stop"}, token="o")
        untouched = next(
            row for row in store.snapshot()["attempt"] if row["id"] == other_root["id"]
        )
        assert untouched["state"] == "unknown" and not untouched.get("cancel_requested")
        denied = await post(
            "/managed/children/grant", request | {"request_key": "later"}, 409
        )
        assert denied["code"] == "child_not_allocated"
        recovered = await post("/managed/children/grant", request)
        assert (
            recovered["binding"] == result["binding"]
            and not recovered["launch_allowed"]
        )
