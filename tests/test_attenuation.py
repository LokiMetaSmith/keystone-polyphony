import pytest
from unittest.mock import AsyncMock
from src.liminal_bridge.mesh import LiminalMesh


@pytest.fixture
def mesh():
    m = LiminalMesh("test-secret", db_path=":memory:")
    m._send_to_sidecar = AsyncMock()
    return m


@pytest.mark.asyncio
async def test_contextual_attenuation_filtering(mesh):
    # Mock peer distance
    peer_id = "peer1"

    # 1. Close peer, low urgency -> Should process
    mesh.peer_distances[peer_id] = 2.0
    payload = {
        "type": "thought",
        "origin": peer_id,
        "content": "Close thought",
        "urgency": "low",
    }
    await mesh._handle_payload(payload)
    assert mesh.thoughts[peer_id]["content"] == "Close thought"

    # 2. Far peer, low urgency -> Should NOT process
    mesh.peer_distances[peer_id] = 10.0
    payload = {
        "type": "thought",
        "origin": peer_id,
        "content": "Far thought",
        "urgency": "low",
    }
    await mesh._handle_payload(payload)
    assert mesh.thoughts[peer_id]["content"] == "Close thought"  # Unchanged

    # 3. Far peer, high urgency -> Should process
    payload = {
        "type": "thought",
        "origin": peer_id,
        "content": "Urgent thought",
        "urgency": "high",
    }
    await mesh._handle_payload(payload)
    assert mesh.thoughts[peer_id]["content"] == "Urgent thought"


@pytest.mark.asyncio
async def test_broadcast_attenuation(mesh):
    # This checks if the urgency flag is passed through the stack to broadcast
    await mesh.share_thought("Test thought", urgency="high")

    # Check the last call to _send_to_sidecar
    args, _ = mesh._send_to_sidecar.call_args
    # args[0] is "broadcast", args[1] is {"e": encrypted_data}
    # We need to decrypt it to check the payload
    encrypted_data = args[1]["e"]
    decrypted_payload = mesh._decrypt(encrypted_data)
    assert decrypted_payload["urgency"] == "high"
