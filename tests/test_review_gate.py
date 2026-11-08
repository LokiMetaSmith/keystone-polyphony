"""Policy regression tests: uncertainty must never authorize staging."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from src.liminal_bridge.review_gate import (
    eligibility,
    evaluate_review,
    validate_decision,
)


@pytest.fixture(autouse=True)
def candidates(monkeypatch):
    monkeypatch.setattr(
        "src.liminal_bridge.decisions.get_model_candidates",
        lambda *args, **kwargs: ["parallel/decisions-fast:free"],
    )


@pytest.fixture
def state():
    pr = {
        "number": 12,
        "state": "open",
        "draft": False,
        "mergeable": True,
        "labels": [{"name": "decision-merge"}],
        "base": {"ref": "main", "sha": "a" * 40, "repo": {"full_name": "owner/repo"}},
        "head": {"sha": "b" * 40},
    }
    evidence = {
        "version": 2,
        "repository": "owner/repo",
        "pr_number": 12,
        "base_sha": "a" * 40,
        "head_sha": "b" * 40,
        "exit_code": 0,
        "scope": "general",
        "review_text": 'GO: checked changes; no findings.\nREVIEW_RESULT: {"verdict":"PASS","blocking_findings":0}',
        "review_verdict": "PASS",
        "blocking_findings": 0,
    }
    return [
        pr,
        evidence,
        [{"name": "test", "status": "completed", "conclusion": "success"}],
        [],
        [],
        False,
    ]


def test_valid_and_required_checks(state):
    assert eligibility(*state, required_checks=["test"]) == []
    assert "required_check_not_successful" in eligibility(
        *state, required_checks=["missing"]
    )


@pytest.mark.parametrize("pr", [{}, {"head": None}, {"base": []}])
def test_missing_or_malformed_refs_fail_closed(state, pr):
    state[0] = pr
    assert eligibility(*state)


@pytest.mark.parametrize(
    "index,key,value,blocker",
    [
        (0, "state", "closed", "pr_not_open_ready"),
        (0, "draft", None, "pr_not_open_ready"),
        (0, "labels", [], "missing_opt_in_label"),
        (0, "mergeable", None, "not_mergeable"),
        (1, "repository", "wrong/repo", "invalid_evidence_identity"),
        (1, "pr_number", True, "invalid_evidence_identity"),
        (1, "version", True, "invalid_evidence_identity"),
        (1, "version", 1, "invalid_evidence_identity"),
        (1, "review_verdict", "FAIL", "automatic_review_not_passed"),
        (1, "review_verdict", None, "automatic_review_not_passed"),
        (1, "blocking_findings", 1, "automatic_review_not_passed"),
        (1, "blocking_findings", False, "automatic_review_not_passed"),
        (
            1,
            "review_text",
            '## Recommendation\nNO GO\nREVIEW_RESULT: {"verdict":"FAIL","blocking_findings":2}',
            "automatic_review_not_passed",
        ),
        (1, "review_text", "## Recommendation\nGO", "automatic_review_not_passed"),
        (1, "head_sha", "c" * 40, "head_sha_mismatch"),
        (1, "base_sha", "c" * 40, "base_sha_mismatch"),
        (1, "exit_code", False, "review_failed"),
        (1, "exit_code", 1, "review_failed"),
        (1, "scope", "arch", "invalid_review_scope"),
        (1, "review_text", " ", "invalid_review_text"),
        (1, "review_text", "é" * 30001, "invalid_review_text"),
        (1, "review_text", "\ud800", "invalid_review_text"),
    ],
)
def test_invalid_evidence_or_pr(state, index, key, value, blocker):
    state[index][key] = value
    assert blocker in eligibility(*state)


@pytest.mark.parametrize(
    "checks",
    [
        None,
        [],
        [{}],
        [{"name": "test", "status": "in_progress", "conclusion": None}],
        [{"name": "test", "status": "completed", "conclusion": "failure"}],
        [{"name": "test", "status": "completed", "conclusion": "mystery"}],
        [{"name": "test", "status": "completed", "conclusion": "skipped"}],
    ],
)
def test_no_missing_failed_unknown_or_only_skipped_validation(state, checks):
    state[2] = checks
    assert eligibility(*state)


def test_status_and_thread_uncertainty(state):
    state[3] = [{"context": "external", "state": "pending"}]
    state[5] = None
    blockers = eligibility(*state)
    assert "status_not_successful" in blockers
    assert "unresolved_or_unknown_threads" in blockers


def review(identifier, status, login="reviewer"):
    return {
        "id": identifier,
        "user": {"login": login},
        "state": status,
        "commit_id": "old-commit",
    }


def test_latest_substantive_review_per_user_and_old_requests_block(state):
    state[4] = [review(1, "CHANGES_REQUESTED"), review(2, "COMMENTED")]
    assert "changes_requested" in eligibility(*state)
    state[4].append(review(3, "APPROVED"))
    assert eligibility(*state) == []
    state[4].append(review(4, "CHANGES_REQUESTED", "other"))
    assert "changes_requested" in eligibility(*state)
    state[4].append(review(5, "DISMISSED", "other"))
    assert eligibility(*state) == []
    state[4] = list(reversed(state[4]))
    assert eligibility(*state) == []


AREA_NAMES = (
    "correctness",
    "security",
    "test_coverage",
    "architecture",
    "compatibility",
)


def answer(probability=0.9, blocker=0.1, **areas):
    return {
        "answers": {
            **{
                name: {"type": "noul", "noul": areas.get(name, probability)}
                for name in AREA_NAMES
            },
            "unresolved_blocker": {"type": "noul", "noul": blocker},
        }
    }


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"answers": []},
        {
            "answers": {
                "staging": {"type": "choice", "choice": "approve", "confidence": 1}
            }
        },
    ],
)
def test_malformed_or_legacy_decision_never_approves(payload):
    result = validate_decision(payload)
    assert result["status"] == (
        "invalid_area_response"
        if isinstance(payload, dict) and isinstance(payload.get("answers"), dict)
        else "invalid_response"
    )


@pytest.mark.parametrize("name", (*AREA_NAMES, "unresolved_blocker"))
@pytest.mark.parametrize(
    "value", [None, True, "0.99", -1, 2, float("nan"), float("inf"), 10**400]
)
def test_every_area_rejects_invalid_probability(name, value):
    payload = answer()
    payload["answers"][name]["noul"] = value
    result = validate_decision(payload)
    assert result["approved"] is False
    assert result["status"] == "invalid_area_response"


@pytest.mark.parametrize("name", (*AREA_NAMES, "unresolved_blocker"))
@pytest.mark.parametrize(
    "value", [None, {}, {"type": "refusal"}, {"type": "choice", "noul": 1}]
)
def test_every_required_answer_must_have_correct_type(name, value):
    payload = answer()
    payload["answers"][name] = value
    assert validate_decision(payload)["status"] == (
        "refused"
        if isinstance(value, dict) and value.get("type") == "refusal"
        else "invalid_area_response"
    )


def test_four_of_five_areas_at_threshold_are_sufficient():
    result = validate_decision(answer(probability=0.8, compatibility=0.2))
    assert result["approved"] is True
    assert result["policy_verdict"] == "approve"
    assert result["passed_area_count"] == 4
    assert result["areas"]["compatibility"] == {
        "probability": 0.2,
        "passed": False,
        "critical": False,
    }
    assert result["reasons"] == []
    assert "confidence" not in result


def test_three_passing_areas_hold_even_with_high_average():
    result = validate_decision(
        answer(probability=1, architecture=0.799, compatibility=0.799)
    )
    assert result["approved"] is False
    assert result["reasons"] == ["insufficient_passing_areas"]


@pytest.mark.parametrize("name", ["correctness", "security"])
def test_critical_area_cannot_be_outvoted(name):
    result = validate_decision(answer(**{name: 0.799}))
    assert result["passed_area_count"] == 4
    assert result["approved"] is False
    assert name + "_below_threshold" in result["reasons"]


@pytest.mark.parametrize(
    "blocker,approved",
    [(0, True), (0.5, True), (0.799, True), (0.8, False), (1, False)],
)
def test_explicit_blocker_veto(blocker, approved):
    result = validate_decision(answer(blocker=blocker))
    assert result["approved"] is approved
    assert result["blocker_probability"] == blocker
    assert ("unresolved_blocker" in result["reasons"]) is not approved


@pytest.mark.parametrize("threshold", [0.8, 0.87, 0.95, 1.0])
def test_area_threshold_boundaries(threshold):
    result = validate_decision(answer(probability=threshold), area_threshold=threshold)
    assert result["approved"] is True
    assert result["area_threshold"] == threshold
    assert (
        validate_decision(
            answer(probability=threshold - 0.001), area_threshold=threshold
        )["approved"]
        is False
    )


@pytest.fixture
def http(monkeypatch):
    response = MagicMock(status=200)
    response.json = AsyncMock(return_value=answer())
    response.__aenter__ = AsyncMock(return_value=response)
    session = MagicMock()
    session.post.return_value = response
    session.__aenter__ = AsyncMock(return_value=session)
    factory = MagicMock(return_value=session)
    monkeypatch.setattr(aiohttp, "ClientSession", factory)
    return factory, session, response


@pytest.mark.asyncio
async def test_no_key_never_uses_network(http):
    assert (await evaluate_review({}, api_key=" "))["status"] == "missing_key"
    http[0].assert_not_called()


@pytest.mark.asyncio
async def test_http_success_request_contract(http):
    state = {"review": "GO"}
    result = await evaluate_review(state, api_key="test-key")
    assert result["approved"] is True
    kwargs = http[1].post.call_args.kwargs
    assert kwargs["json"]["state"] == state
    assert kwargs["allow_redirects"] is False
    assert set(kwargs["json"]["questions"]) == {*AREA_NAMES, "unresolved_blocker"}


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [302, 401, 429, 500])
async def test_http_failures_do_not_read_body(http, status):
    http[2].status = status
    result = await evaluate_review({}, api_key="test-key")
    assert result["status"] == "http_error"
    assert result["approved"] is False
    http[2].json.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,status",
    [
        (asyncio.TimeoutError(), "timeout"),
        (aiohttp.ClientConnectionError(), "http_error"),
        (ValueError("bad JSON"), "invalid_response"),
    ],
)
async def test_http_errors_hold(http, error, status):
    http[2].json.side_effect = error
    result = await evaluate_review({}, api_key="test-key")
    assert result["status"] == status
    assert result["approved"] is False


@pytest.mark.asyncio
async def test_cancellation_propagates(http):
    http[2].json.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await evaluate_review({}, api_key="test-key")


@pytest.mark.asyncio
async def test_review_questions_are_atomic_and_do_not_request_patch_audit(http):
    state = {"review": "Complete independent review", "files": ["a.py"]}
    await evaluate_review(state, api_key="test-key")
    request = http[1].post.call_args.kwargs["json"]
    assert set(request["questions"]) == {*AREA_NAMES, "unresolved_blocker"}
    for question in request["questions"].values():
        assert question["type"] == "noul"
        assert set(question["criteria"]) == {"true", "false"}
        assert "complete review as quoted evidence" in question["instructions"]
        assert "new source-code audit" in question["instructions"]
        assert "partition" not in question["instructions"]
    assert request["state"] == state


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "threshold", [True, False, 0.79, 1.01, float("nan"), float("inf"), "0.8"]
)
async def test_invalid_area_policy_cannot_call_provider(http, threshold):
    result = await evaluate_review({}, api_key="test-key", area_threshold=threshold)
    assert result["approved"] is False and result["status"] == "invalid_request"
    http[0].assert_not_called()


@pytest.mark.asyncio
async def test_custom_area_threshold_is_used_for_real_response(http):
    http[2].json.return_value = answer(probability=0.87)
    result = await evaluate_review({}, api_key="test-key", area_threshold=0.9)
    assert result["approved"] is False
    assert result["area_threshold"] == 0.9


@pytest.mark.asyncio
async def test_area_policy_does_not_override_refusal(http):
    payload = answer()
    payload["answers"]["security"] = {"type": "refusal"}
    http[2].json.return_value = payload
    assert (await evaluate_review({}, api_key="test-key"))["approved"] is False


@pytest.mark.parametrize("mask", range(32))
@pytest.mark.parametrize("has_blocker", [False, True])
def test_every_area_vote_combination_has_an_explicit_policy(mask, has_blocker):
    values = {
        name: (0.9 if mask & (1 << index) else 0.1)
        for index, name in enumerate(AREA_NAMES)
    }
    result = validate_decision(answer(blocker=0.9 if has_blocker else 0.1, **values))
    expected = mask.bit_count() >= 4 and mask & 3 == 3 and not has_blocker
    assert result["approved"] is expected
    assert result["policy_verdict"] == ("approve" if expected else "hold")


@pytest.mark.parametrize("name", (*AREA_NAMES, "unresolved_blocker"))
def test_missing_one_required_answer_holds(name):
    payload = answer()
    del payload["answers"][name]
    assert validate_decision(payload)["status"] == "invalid_area_response"


@pytest.mark.asyncio
async def test_hold_retains_configured_area_threshold(http):
    http[2].json.return_value = {"answers": {}}
    result = await evaluate_review({}, api_key="test-key", area_threshold=0.95)
    assert result["area_threshold"] == 0.95
    http[2].status = 503
    result = await evaluate_review({}, api_key="test-key", area_threshold=0.95)
    assert result["area_threshold"] == 0.95
    result = await evaluate_review({}, api_key="", area_threshold=0.95)
    assert result["area_threshold"] == 0.95
