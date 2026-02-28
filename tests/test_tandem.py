import pytest
from unittest.mock import AsyncMock, MagicMock
from src.liminal_bridge.mesh import LiminalMesh


@pytest.fixture
def mesh():
    m = LiminalMesh("test-secret", db_path=":memory:")
    m._send_to_sidecar = AsyncMock()
    return m


@pytest.mark.asyncio
async def test_tandem_sync_broadcast(mesh):
    # Sync physical state
    state = {"force_x": 1.2, "force_y": -0.5}
    await mesh.tandem_sync("peer1", state)

    # Check if broadcast was called with high urgency
    args, _ = mesh._send_to_sidecar.call_args
    encrypted_data = args[1]["e"]
    payload = mesh._decrypt(encrypted_data)
    assert payload["type"] == "tandem_sync"
    assert payload["target"] == "peer1"
    assert payload["state"]["force_x"] == 1.2
    assert payload["urgency"] == "high"


@pytest.mark.asyncio
async def test_tandem_sync_callback(mesh):
    # Setup callback
    callback = MagicMock()
    mesh.on_tandem_sync = callback

    # Simulate receiving tandem sync
    payload = {
        "type": "tandem_sync",
        "origin": "peer1",
        "target": mesh.node_id,
        "state": {"haptic": 0.8},
        "urgency": "high",
    }
    await mesh._handle_payload(payload)

    # Verify callback was triggered
    callback.assert_called_once_with("peer1", {"haptic": 0.8})
