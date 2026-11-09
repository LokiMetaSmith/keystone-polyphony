"""Transport overlap, targeted commands, and restart-safe deduplication."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.liminal_bridge.mesh import LiminalMesh
from src.liminal_bridge.storage import SQLiteStorageProvider


def make_mesh(tmp_path, name):
    node = LiminalMesh(
        "overlap-test-key",
        storage_provider=SQLiteStorageProvider(str(tmp_path / f"{name}.db")),
        identity_path=str(tmp_path / f"{name}.pem"),
    )
    node.capabilities = ["coder"]
    node.status = "idle"
    return node


@pytest.mark.asyncio
async def test_duplicate_signed_envelopes_execute_callback_only_once(tmp_path):
    source = make_mesh(tmp_path, "sender")
    target = make_mesh(tmp_path, "receiver")
    source._send_to_sidecar = AsyncMock()
    source.mqtt_host = "broker"
    source._mqtt_client = SimpleNamespace(publish=AsyncMock())
    received = []

    async def handler(origin, command):
        received.append((origin, command))

    target.on_command_request = handler
    await source.broadcast_command(
        {"type": "execute", "payload": "inspect"},
        target=target.node_id,
        capabilities=["coder"],
        status_filter="idle",
    )

    _, encoded = source._mqtt_client.publish.call_args.args
    mqtt = json.loads(encoded)
    dht = source._send_to_sidecar.call_args.args[1]
    assert mqtt == dht
    assert len(source._decrypt(mqtt["e"])["message_id"]) == 32

    for envelope in (mqtt, dht, mqtt):
        await target._handle_message(
            {"type": "message", "peer_id": "test-peer", "payload": envelope}
        )
    await asyncio.sleep(0)
    assert received == [(source.node_id, {"type": "execute", "payload": "inspect"})]

    # A new process with the same durable storage cannot replay the command.
    restarted = make_mesh(tmp_path, "receiver")
    restarted.on_command_request = handler
    await restarted._handle_message(
        {"type": "message", "peer_id": "test-peer", "payload": mqtt}
    )
    await asyncio.sleep(0)
    assert len(received) == 1


@pytest.mark.asyncio
async def test_target_and_capabilities_are_conjunctive(tmp_path):
    node = make_mesh(tmp_path, "recipient")
    command = {"type": "execute", "payload": "sensitive"}
    received = []
    node.on_command_request = AsyncMock(side_effect=lambda *args: received.append(args))
    payload = {
        "type": "command_request",
        "origin": "peer",
        "message_id": "f" * 32,
        "target": "different-node",
        "capabilities": ["coder"],
        "status_filter": "idle",
        "command": command,
    }
    await node._handle_payload(payload)
    await asyncio.sleep(0)
    assert not received

    payload["target"] = node.node_id
    payload["capabilities"] = ["coder", "gpu"]
    await node._handle_payload(payload)
    await asyncio.sleep(0)
    assert not received

    payload["capabilities"] = ["coder"]
    payload["status_filter"] = "busy"
    await node._handle_payload(payload)
    await asyncio.sleep(0)
    assert not received

    payload["status_filter"] = "idle"
    await node._handle_payload(payload)
    await asyncio.sleep(0)
    assert len(received) == 1


@pytest.mark.asyncio
async def test_invalid_message_id_cannot_bypass_deduplication(tmp_path):
    node = make_mesh(tmp_path, "recipient")
    node.on_command_request = AsyncMock()
    await node._handle_payload(
        {
            "type": "command_request",
            "origin": "peer",
            "target": node.node_id,
            "message_id": "invalid-identifier",
            "command": {"type": "execute"},
        }
    )
    await asyncio.sleep(0)
    node.on_command_request.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_envelope_without_id_is_still_received(tmp_path):
    node = make_mesh(tmp_path, "recipient")
    node.on_command_request = AsyncMock()
    await node._handle_payload(
        {
            "type": "command_request",
            "origin": "peer",
            "target": node.node_id,
            "command": {"type": "ping"},
        }
    )
    await asyncio.sleep(0)
    node.on_command_request.assert_awaited_once()


@pytest.mark.asyncio
async def test_reused_payload_is_a_new_logical_broadcast(tmp_path):
    node = make_mesh(tmp_path, "sender")
    node._send_to_sidecar = AsyncMock()
    payload = {"type": "thought", "content": "repeat intentionally"}
    await node.broadcast(payload)
    first = node._send_to_sidecar.call_args.args[1]
    await node.broadcast(payload)
    second = node._send_to_sidecar.call_args.args[1]
    assert node._decrypt(first["e"])["message_id"] != node._decrypt(second["e"])["message_id"]
