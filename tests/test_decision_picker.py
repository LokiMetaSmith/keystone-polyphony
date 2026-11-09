"""Availability failover cannot shop for a more permissive decision."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.liminal_bridge.decisions import DecisionAdvisor
from src.liminal_bridge.review_gate import evaluate_review


@pytest.fixture(params=["coordination", "staging"])
def client(request, monkeypatch):
    kind = request.param
    monkeypatch.setattr(
        "src.liminal_bridge.decisions.get_model_candidates",
        lambda *args, **kwargs: ["best:free", "next:free"],
    )
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    monkeypatch.setattr("aiohttp.ClientSession", MagicMock(return_value=session))

    async def evaluate(**kwargs):
        if kind == "staging":
            return await evaluate_review({}, api_key="key", **kwargs)
        return await DecisionAdvisor(enabled=True, api_key="key", **kwargs).evaluate({})

    def answer(choice=None, confidence=0.99, refusal=False):
        if kind == "staging":
            names = (
                "correctness",
                "security",
                "test_coverage",
                "architecture",
                "compatibility",
                "unresolved_blocker",
            )
            values = {name: confidence for name in names}
            values["unresolved_blocker"] = 0.99 if choice == "hold" else 0.1
            return {
                "answers": {
                    name: (
                        {"type": "refusal"}
                        if refusal
                        else {"type": "noul", "noul": values[name]}
                    )
                    for name in names
                }
            }
        value = (
            {"type": "refusal"}
            if refusal
            else {
                "type": "choice",
                "choice": choice or "continue",
                "confidence": confidence,
            }
        )
        return {"answers": {kind: value}}

    def response(payload=None, status=200):
        response = MagicMock(status=status)
        response.__aenter__ = AsyncMock(return_value=response)
        response.json = AsyncMock(return_value=payload)
        return response

    return kind, evaluate, answer, response, session


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [404, 429, 503, "malformed", "transport", "timeout"]
)
async def test_service_failure_tries_next_ranked_model(client, failure):
    _, evaluate, answer, response, session = client
    first = response({}, failure if isinstance(failure, int) else 200)
    if failure == "transport":
        first.json.side_effect = OSError("offline")
    elif failure == "timeout":
        first.json.side_effect = asyncio.TimeoutError()
    session.post.side_effect = [first, response(answer())]
    result = await evaluate()
    assert result["status"] == "decision"
    assert result["model"] == "next:free"
    assert [call.kwargs["json"]["model"] for call in session.post.call_args_list] == [
        "best:free",
        "next:free",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["negative", "low_confidence", "refusal"])
async def test_substantive_negative_never_tries_another_model(client, outcome):
    kind, evaluate, answer, response, session = client
    payload = answer(
        choice=(
            ("hold" if kind == "staging" else "consult_architect")
            if outcome == "negative"
            else None
        ),
        confidence=0.1 if outcome == "low_confidence" else 0.99,
        refusal=outcome == "refusal",
    )
    session.post.return_value = response(payload)
    result = await evaluate()
    assert result["model"] == "best:free"
    assert session.post.call_count == 1
    if kind == "staging":
        assert result["approved"] is False
    else:
        assert result["action"] == "consult_architect"


@pytest.mark.asyncio
async def test_explicit_model_skips_catalog_and_fallback(client, monkeypatch):
    _, evaluate, _, response, session = client
    picker = MagicMock(side_effect=AssertionError("catalog must not be called"))
    monkeypatch.setattr("src.liminal_bridge.decisions.get_model_candidates", picker)
    session.post.return_value = response(status=503)
    result = await evaluate(model="explicit:model")
    assert result["model"] == "explicit:model"
    assert session.post.call_count == 1
    picker.assert_not_called()


@pytest.mark.asyncio
async def test_catalog_is_inside_total_timeout(client, monkeypatch):
    _, evaluate, _, _, session = client
    import time

    def slow_catalog(*args, **kwargs):
        time.sleep(0.05)
        return ["best:free"]

    monkeypatch.setattr(
        "src.liminal_bridge.decisions.get_model_candidates", slow_catalog
    )
    result = await evaluate(timeout=0.005)
    assert result["status"] == "timeout"
    session.post.assert_not_called()


@pytest.mark.asyncio
async def test_empty_catalog_fails_closed(client, monkeypatch):
    _, evaluate, _, _, session = client
    monkeypatch.setattr(
        "src.liminal_bridge.decisions.get_model_candidates", lambda *a, **k: []
    )
    result = await evaluate()
    assert result["status"] == "no_models"
    session.post.assert_not_called()


@pytest.mark.asyncio
async def test_auth_failure_does_not_try_another_model(client):
    _, evaluate, _, response, session = client
    session.post.return_value = response(status=401)
    result = await evaluate()
    assert result["status"] == "http_error"
    assert session.post.call_count == 1


@pytest.mark.asyncio
async def test_total_timeout_preserves_actual_model(client):
    _, evaluate, _, response, session = client
    first = response()

    async def slow_json():
        await asyncio.sleep(1)

    first.json.side_effect = slow_json
    session.post.return_value = first
    result = await evaluate(timeout=0.01)
    assert result["status"] == "timeout"
    assert result["model"] == "best:free"
    assert session.post.call_count == 1


@pytest.mark.asyncio
async def test_candidate_attempts_are_bounded(client, monkeypatch):
    _, evaluate, _, response, session = client
    monkeypatch.setattr(
        "src.liminal_bridge.decisions.get_model_candidates",
        lambda *a, **k: [f"model-{n}:free" for n in range(10)],
    )
    session.post.return_value = response(status=503)
    result = await evaluate()
    assert result["status"] == "http_error"
    assert session.post.call_count == 3
    assert result["model"] == "model-2:free"


@pytest.mark.asyncio
async def test_auto_spelling_matches_picker(client):
    _, evaluate, answer, response, session = client
    session.post.return_value = response(answer())
    result = await evaluate(model=" AUTO ")
    assert result["model"] == "best:free"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload,status",
    [
        ({"answers": {}}, "invalid_area_response"),
        (
            {"answers": {"correctness": {"type": "noul", "noul": 0.99}}},
            "invalid_area_response",
        ),
        (
            {"answers": {"correctness": {"type": "noul", "noul": True}}},
            "invalid_area_response",
        ),
        ({"answers": {"correctness": {"type": "refusal"}}}, "refused"),
    ],
)
async def test_invalid_area_evidence_never_shops_for_another_model(
    client, payload, status
):
    kind, evaluate, _, response, session = client
    if kind != "staging":
        return
    session.post.return_value = response(payload)
    result = await evaluate()
    assert result["approved"] is False
    assert result["status"] == status
    assert result["model"] == "best:free"
    assert session.post.call_count == 1
