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


def answer(choice="approve", confidence=0.99):
    return {
        "answers": {
            "staging": {"type": "choice", "choice": choice, "confidence": confidence}
        }
    }


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"answers": []},
        {"answers": {"staging": {"type": "refusal"}}},
        answer("execute"),
        answer(confidence=float("nan")),
        answer(confidence=float("inf")),
        answer(confidence=True),
        answer(confidence="0.99"),
        answer(confidence=None),
        answer(confidence=-1),
        answer(confidence=10**400),
    ],
)
def test_malformed_decision_never_approves(payload):
    result = validate_decision(payload)
    assert result["approved"] is False
    assert result["status"] == "invalid_response"


def test_decision_threshold_and_hold():
    assert validate_decision(answer(confidence=0.95))["approved"] is True
    assert validate_decision(answer(confidence=0.949))["status"] == "low_confidence"
    assert validate_decision(answer("hold"))["approved"] is False
    assert validate_decision(answer(), minconfidence=0.5)["approved"] is False


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
    assert set(kwargs["json"]["questions"]["staging"]["criteria"]) == {
        "approve",
        "hold",
    }


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
async def test_partition_policy_is_in_trusted_question_not_only_untrusted_state(http):
    state = {
        "chunk": {"index": 2, "count": 3},
        "diff": "+second partition",
        "diff_manifest": [{"header": "diff --git a/test b/test", "sha256": "abc"}],
    }
    await evaluate_review(state, api_key="test-key")
    request = http[1].post.call_args.kwargs["json"]
    instructions = request["questions"]["staging"]["instructions"]
    assert "one ordered partition of the complete change" in instructions
    assert "full independent review" in instructions
    assert "requires every partition to approve" in instructions
    assert "Missing expected partition evidence still holds" in instructions
    assert request["state"] == state
