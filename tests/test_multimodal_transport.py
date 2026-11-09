import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.liminal_bridge.mesh import LiminalMesh
from src.liminal_bridge.storage import SQLiteStorageProvider


@pytest.fixture
def mesh(tmp_path):
    node = LiminalMesh(
        "transport-test-secret",
        storage_provider=SQLiteStorageProvider(str(tmp_path / "mesh.db")),
        identity_path=str(tmp_path / "identity.pem"),
    )
    node._send_to_sidecar = AsyncMock()
    return node


def assert_envelope(mesh, envelope, payload):
    assert mesh._decrypt(envelope["e"]) == payload
    assert envelope["p"] == mesh.public_key_hex
    mesh.public_key.verify(bytes.fromhex(envelope["s"]), envelope["e"].encode())


def mock_ble(monkeypatch, mesh, peers, failed=()):
    devices = {}
    clients = {}
    for address, matching in peers:
        device = SimpleNamespace(address=address)
        advertisement = SimpleNamespace(
            service_uuids=[mesh._ble_service_uuid.upper() if matching else "unrelated"]
        )
        devices[address] = (device, advertisement)
        client = AsyncMock()
        client.__aenter__.return_value = client
        if address in failed:
            client.write_gatt_char.side_effect = OSError("disconnected")
        clients[address] = client
    scanner = SimpleNamespace(discover=AsyncMock(return_value=devices))
    factory = Mock(side_effect=lambda device: clients[device.address])
    monkeypatch.setitem(
        sys.modules,
        "bleak",
        SimpleNamespace(
            BleakScanner=scanner,
            BleakClient=factory,
        ),
    )
    mesh.ble_enabled = True
    return scanner, factory, clients


@pytest.mark.asyncio
async def test_ble_broadcast_reaches_all_matching_peers(monkeypatch, mesh):
    scanner, factory, clients = mock_ble(
        monkeypatch,
        mesh,
        [
            ("peer-1", True),
            ("other", False),
            ("peer-2", True),
        ],
    )
    payload = {"type": "thought", "content": "hello"}

    result = await mesh.broadcast_micro(payload)
    assert result["ble"] == "submitted"
    assert result["ble_attempted"] == 2
    assert result["ble_submitted"] == 2
    assert result["dht"] == "submitted"

    scanner.discover.assert_awaited_once_with(timeout=3.0, return_adv=True)
    assert factory.call_count == 2
    for address in ("peer-1", "peer-2"):
        clients[address].write_gatt_char.assert_awaited_once()
        args, kwargs = clients[address].write_gatt_char.call_args
        assert args[0] == mesh._ble_characteristic_uuid
        assert kwargs == {"response": True}
        assert_envelope(mesh, json.loads(args[1]), payload)
    clients["other"].write_gatt_char.assert_not_awaited()
    mesh._send_to_sidecar.assert_awaited_once()


@pytest.mark.asyncio
async def test_ble_continues_after_peer_failure_without_duplicate_dht(
    monkeypatch, mesh
):
    _, _, clients = mock_ble(
        monkeypatch,
        mesh,
        [
            ("unreachable", True),
            ("reachable", True),
        ],
        failed=("unreachable",),
    )

    result = await mesh.broadcast_micro({"type": "test"})
    assert result["ble"] == "partial"
    assert result["ble_attempted"] == 2
    assert result["ble_submitted"] == 1

    clients["unreachable"].write_gatt_char.assert_awaited_once()
    clients["reachable"].write_gatt_char.assert_awaited_once()
    mesh._send_to_sidecar.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["no-match", "write-failure", "scan-failure"])
async def test_ble_falls_back_when_nothing_delivered(monkeypatch, mesh, scenario):
    scanner, _, _ = mock_ble(
        monkeypatch, mesh, [("peer", scenario == "write-failure")], failed=("peer",)
    )
    if scenario == "scan-failure":
        scanner.discover.side_effect = OSError("adapter unavailable")
    payload = {"type": "test"}

    await mesh.broadcast_micro(payload)

    mesh._send_to_sidecar.assert_awaited_once()
    operation, envelope = mesh._send_to_sidecar.call_args.args
    assert operation == "broadcast"
    assert_envelope(mesh, envelope, payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["broadcast_macro", "broadcast_micro"])
async def test_disabled_transport_uses_signed_encrypted_dht(mesh, transport):
    payload = {"type": "test", "content": "private"}

    await getattr(mesh, transport)(payload)

    mesh._send_to_sidecar.assert_awaited_once()
    operation, envelope = mesh._send_to_sidecar.call_args.args
    assert operation == "broadcast"
    assert_envelope(mesh, envelope, payload)


@pytest.mark.asyncio
async def test_mqtt_reuses_client_and_preserves_envelope(mesh):
    mesh.mqtt_host = "broker"
    mesh._mqtt_client = SimpleNamespace(publish=AsyncMock())
    payload = {"type": "test"}

    result = await mesh.broadcast_macro(payload)
    assert result["mqtt"] == "submitted"
    assert result["dht"] == "submitted"

    mesh._mqtt_client.publish.assert_awaited_once()
    topic, encoded = mesh._mqtt_client.publish.call_args.args
    assert topic == f"keystone/{mesh.topic}/macro"
    assert_envelope(mesh, json.loads(encoded), payload)
    mesh._send_to_sidecar.assert_awaited_once()
    assert mesh._send_to_sidecar.call_args.args[1] == json.loads(encoded)


@pytest.mark.asyncio
async def test_mqtt_publish_failure_uses_dht(mesh):
    mesh.mqtt_host = "broker"
    mesh._mqtt_client = SimpleNamespace(
        publish=AsyncMock(side_effect=OSError("offline"))
    )
    payload = {"type": "test"}

    result = await mesh.broadcast_macro(payload)
    assert result["mqtt"] == "failed"
    assert result["dht"] == "submitted"

    mesh._send_to_sidecar.assert_awaited_once()
    assert_envelope(mesh, mesh._send_to_sidecar.call_args.args[1], payload)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "urgency,distance,route",
    [
        ("high", 0.5, "macro"),
        ("low", 6.0, "macro"),
        ("low", 0.5, "micro"),
        ("low", 2.0, "dht"),
        ("low", None, "dht"),
    ],
)
async def test_broadcast_routing(mesh, urgency, distance, route):
    mesh.broadcast_macro = AsyncMock()
    mesh.broadcast_micro = AsyncMock()
    if distance is not None:
        mesh.update_peer_distance("peer", distance)
    payload = {"type": "test"}

    await mesh.broadcast(payload, urgency=urgency)

    assert mesh.broadcast_macro.await_count == (route == "macro")
    assert mesh.broadcast_micro.await_count == (route == "micro")
    assert mesh._send_to_sidecar.await_count == (route == "dht")
    assert payload["origin"] == mesh.node_id
    assert payload["sender_pubkey"] == mesh.public_key_hex
    assert payload["urgency"] == urgency
    assert "timestamp" in payload
    assert payload["vc"] == mesh.vector_clock


@pytest.mark.asyncio
async def test_mqtt_success_dht_failure_preserves_available_route(mesh):
    mesh.mqtt_host = "broker"
    mesh._mqtt_client = SimpleNamespace(publish=AsyncMock())
    mesh._send_to_sidecar.side_effect = OSError("dht offline")
    result = await mesh.broadcast_macro({"type": "thought", "content": "test"})
    assert result["mqtt"] == "submitted"
    assert result["dht"] == "failed"
    mesh._mqtt_client.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_all_transport_failures_propagate(mesh):
    mesh.mqtt_host = "broker"
    mesh._mqtt_client = SimpleNamespace(
        publish=AsyncMock(side_effect=OSError("mqtt offline"))
    )
    mesh._send_to_sidecar.side_effect = OSError("dht offline")
    with pytest.raises(OSError, match="dht offline"):
        await mesh.broadcast_macro({"type": "thought", "content": "test"})


@pytest.mark.asyncio
async def test_public_broadcast_exposes_partial_delivery_outcome(mesh):
    async def attempted(payload):
        return {
            "message_id": payload["message_id"],
            "mqtt": "submitted",
            "dht": "failed",
        }

    mesh.broadcast_macro = AsyncMock(side_effect=attempted)
    result = await mesh.broadcast({"type": "thought"}, urgency="high")
    assert result["mqtt"] == "submitted"
    assert result["dht"] == "failed"
    assert len(result["message_id"]) == 32


@pytest.mark.asyncio
async def test_default_broadcast_reports_dht_submission(mesh):
    result = await mesh.broadcast({"type": "thought"})
    assert result["dht"] == "submitted"
    assert len(result["message_id"]) == 32
