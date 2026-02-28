import pytest
from unittest.mock import AsyncMock
from src.liminal_bridge.mesh import LiminalMesh


@pytest.fixture
def mesh():
    m = LiminalMesh("test-secret", db_path=":memory:")
    m._send_to_sidecar = AsyncMock()
    return m


@pytest.mark.asyncio
async def test_mesh_health_degradation(mesh):
    # Initial state: healthy (once started and has peers)
    await mesh.start()
    mesh.peers.add("peer1")  # Mock a peer
    assert mesh.get_health_status()["status"] == "healthy"

    # Simulate peer loss
    mesh.peers.clear()
    assert mesh.get_health_status()["status"] == "degraded"
    assert mesh.get_health_status()["reason"] == "No global peers discovered"

    # Simulate sidecar failure
    mesh.running = False
    assert mesh.get_health_status()["status"] == "offline"


@pytest.mark.asyncio
async def test_fallback_logic_trigger(mesh):
    # If degraded, certain actions might change behavior
    # For now, we'll just verify the health reporting
    status = mesh.get_health_status()
    assert "status" in status
