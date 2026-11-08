import asyncio
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from src.liminal_bridge.decisions import (
    DECISIONS_URL,
    DEFAULT_MODEL,
    DecisionAdvisor,
)


@pytest.fixture
def http(monkeypatch):
    response = MagicMock(status=200)
    response.json = AsyncMock()
    response.__aenter__ = AsyncMock(return_value=response)
    session = MagicMock()
    session.post.return_value = response
    session.__aenter__ = AsyncMock(return_value=session)
    factory = MagicMock(return_value=session)
    monkeypatch.setattr(aiohttp, "ClientSession", factory)
    return factory, session, response


def answer(choice="continue", confidence=0.95, **extra):
    return {
        "answers": {
            "coordination": {
                "type": "choice",
                "choice": choice,
                "confidence": confidence,
                **extra,
            }
        }
    }


@pytest.mark.asyncio
async def test_disabled_and_missing_key_never_create_http_session(http, monkeypatch):
    monkeypatch.delenv("LIMINAL_DECISIONS_ENABLED", raising=False)
    factory, _, _ = http
    disabled = await DecisionAdvisor(api_key="test-key").evaluate({})
    missing = await DecisionAdvisor(enabled=True, api_key="").evaluate({})
    assert disabled["status"] == "disabled"
    assert missing["status"] == "missing_key"
    assert disabled["action"] == missing["action"] == "consult_architect"
    factory.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("choice", ["continue", "consult_architect"])
async def test_typed_decision_and_request_contract(http, choice):
    factory, session, response = http
    response.json.return_value = answer(choice, 0.8)
    state = {"context": "routine_check", "batons": {}}
    result = await DecisionAdvisor(enabled=True, api_key="test-key").evaluate(state)
    assert result == {
        "action": choice,
        "status": "decision",
        "source": "decisions",
        "model": DEFAULT_MODEL,
        "confidence": 0.8,
    }
    args, kwargs = session.post.call_args
    assert args == (DECISIONS_URL,)
    assert kwargs["headers"] == {"Authorization": "Bearer test-key"}
    assert kwargs["allow_redirects"] is False
    assert kwargs["json"]["state"] == state
    assert kwargs["json"]["model"] == DEFAULT_MODEL
    question = kwargs["json"]["questions"]["coordination"]
    assert question["type"] == "choice"
    assert set(question["criteria"]) == {"continue", "consult_architect"}
    assert factory.call_args.kwargs["timeout"].total == 5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"answers": []},
        {"answers": {"coordination": {"type": "refusal"}}},
        answer("execute_command"),
        answer(confidence=float("nan")),
        answer(confidence=float("inf")),
        answer(confidence=True),
        answer(confidence="0.99"),
        answer(confidence=None),
        answer(confidence=1.1),
        answer(confidence=-0.1),
        answer(confidence=10**400),
    ],
)
async def test_invalid_or_refused_output_preserves_consultation(http, payload):
    http[2].json.return_value = payload
    result = await DecisionAdvisor(enabled=True, api_key="test-key").evaluate({})
    assert result["action"] == "consult_architect"
    assert result["status"] == "invalid_response"


@pytest.mark.asyncio
async def test_low_confidence_preserves_consultation(http):
    http[2].json.return_value = answer(confidence=0.79)
    result = await DecisionAdvisor(enabled=True, api_key="test-key").evaluate({})
    assert result["action"] == "consult_architect"
    assert result["status"] == "low_confidence"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [302, 401, 429, 500])
async def test_http_failure_preserves_consultation_without_reading_body(http, status):
    http[2].status = status
    result = await DecisionAdvisor(enabled=True, api_key="test-key").evaluate({})
    assert result["action"] == "consult_architect"
    assert result["status"] == "http_error"
    http[2].json.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,status",
    [
        (asyncio.TimeoutError(), "timeout"),
        (aiohttp.ClientConnectionError(), "http_error"),
        (ValueError("malformed JSON"), "invalid_response"),
    ],
)
async def test_request_errors_preserve_consultation(http, error, status):
    http[2].json.side_effect = error
    result = await DecisionAdvisor(enabled=True, api_key="test-key").evaluate({})
    assert result["action"] == "consult_architect"
    assert result["status"] == status


def test_environment_configuration_and_bounded_timeout(monkeypatch):
    monkeypatch.setenv("LIMINAL_DECISIONS_ENABLED", "true")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("LIMINAL_DECISION_MODEL", "example/model")
    monkeypatch.setenv("LIMINAL_DECISION_TIMEOUT", "2.5")
    advisor = DecisionAdvisor()
    assert advisor.enabled is True
    assert advisor.api_key == "test-key"
    assert advisor.model == "example/model"
    assert advisor.timeout == 2.5
    for raw in ("nan", "inf", "invalid", "0", "-1"):
        monkeypatch.setenv("LIMINAL_DECISION_TIMEOUT", raw)
        assert DecisionAdvisor().timeout == 5
    assert DecisionAdvisor(timeout=100).timeout == 30


@pytest.mark.asyncio
async def test_cancellation_propagates(http):
    http[2].json.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await DecisionAdvisor(enabled=True, api_key="test-key").evaluate({})
