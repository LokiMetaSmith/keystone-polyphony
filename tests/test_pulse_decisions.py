import json
from unittest.mock import AsyncMock, Mock

import pytest

from src.liminal_bridge.pulse import Pulse


@pytest.fixture
def components():
    mesh = Mock()
    mesh.thoughts = {"worker": {"content": "private context"}}
    mesh.batons = {}
    mesh.get_all_kv.return_value = {"master_plan": {"backlog": "existing"}}
    mesh.get_kv.side_effect = lambda key: (
        [
            json.dumps(
                {"status": "todo", "priority": "high", "description": "private task"}
            )
        ]
        if key == "swarm_backlog"
        else {"backlog": "existing"}
    )
    mesh.update_kv = AsyncMock()
    mesh.broadcast_command = AsyncMock()
    architect = Mock(consult=AsyncMock(return_value='{"backlog": "updated"}'))
    advisor = Mock(
        evaluate=AsyncMock(return_value={"action": "continue", "status": "decision"})
    )
    return mesh, architect, advisor


@pytest.mark.asyncio
async def test_continue_preserves_plan_and_respects_cooldown(components):
    mesh, architect, advisor = components
    pulse = Pulse(mesh, architect, advisor)
    await pulse.trigger()
    await pulse.trigger()
    advisor.evaluate.assert_awaited_once()
    architect.consult.assert_not_awaited()
    mesh.update_kv.assert_not_awaited()
    mesh.broadcast_command.assert_not_awaited()
    summary = advisor.evaluate.call_args.args[0]
    assert summary["tasks"] == [{"status": "todo", "priority": "high"}]
    assert "private" not in json.dumps(summary)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [
        "disabled",
        "missing_key",
        "timeout",
        "invalid_response",
        "low_confidence",
        "decision",
    ],
)
async def test_consult_and_fallback_keep_architect_behavior(components, status):
    mesh, architect, advisor = components
    advisor.evaluate.return_value = {"action": "consult_architect", "status": status}
    architect.consult.return_value = json.dumps(
        {"commands": [{"target": "worker", "command": "review"}]}
    )
    pulse = Pulse(mesh, architect, advisor)
    await pulse.trigger()
    architect.consult.assert_awaited_once()
    mesh.update_kv.assert_awaited_once_with(
        "master_plan", {"commands": [{"target": "worker", "command": "review"}]}
    )
    mesh.broadcast_command.assert_awaited_once()


@pytest.mark.asyncio
async def test_force_bypasses_advisor_and_cooldown(components):
    mesh, architect, advisor = components
    pulse = Pulse(mesh, architect, advisor)
    await pulse.trigger()
    await pulse.trigger("force")
    advisor.evaluate.assert_awaited_once()
    architect.consult.assert_awaited_once()
    mesh.update_kv.assert_awaited_once()
    assert pulse.last_decision is None


@pytest.mark.asyncio
async def test_continue_cannot_skip_creating_initial_plan(components):
    mesh, architect, advisor = components
    mesh.get_kv.side_effect = lambda key: [] if key == "swarm_backlog" else None
    await Pulse(mesh, architect, advisor).trigger()
    architect.consult.assert_awaited_once()
    mesh.update_kv.assert_awaited_once()


@pytest.mark.asyncio
async def test_summary_limits_tasks_and_ignores_malformed_entries(components):
    mesh, _, advisor = components
    mesh.get_kv.side_effect = lambda key: (
        ["broken", "[]", None] + [json.dumps({"status": "todo"})] * 120
        if key == "swarm_backlog"
        else None
    )
    await Pulse(mesh, components[1], advisor).trigger()
    summary = advisor.evaluate.call_args.args[0]
    assert summary["task_count"] == 120
    assert len(summary["tasks"]) == 100


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "context,category",
    [
        ("baton_released:private/file by node-123", "baton_released"),
        ("manual:private request", "manual"),
        ("private arbitrary trigger", "other"),
    ],
)
async def test_advisor_receives_trigger_category_only(components, context, category):
    mesh, architect, advisor = components
    await Pulse(mesh, architect, advisor).trigger(context)
    summary = advisor.evaluate.call_args.args[0]
    assert summary["context"] == category
    assert "private" not in json.dumps(summary)


@pytest.mark.asyncio
async def test_non_collection_backlog_keeps_consultation_working(components):
    mesh, architect, advisor = components
    mesh.get_kv.side_effect = lambda key: 7 if key == "swarm_backlog" else None
    advisor.evaluate.return_value = {
        "action": "consult_architect",
        "status": "disabled",
    }
    await Pulse(mesh, architect, advisor).trigger()
    architect.consult.assert_awaited_once()
    assert advisor.evaluate.call_args.args[0]["task_count"] == 0
