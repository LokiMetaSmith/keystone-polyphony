import pytest
from unittest.mock import AsyncMock
from src.liminal_bridge.mesh import LiminalMesh


@pytest.fixture
def mesh():
    m = LiminalMesh("test-secret", db_path=":memory:")
    m._send_to_sidecar = AsyncMock()
    return m


@pytest.mark.asyncio
async def test_stigmergy_markers(mesh):
    # Leave a marker
    marker_id = "marker123"
    await mesh.leave_marker(
        marker_id,
        marker_type="work_in_progress",
        location="zone_a",
        payload={"task": "assembly"},
    )

    # Verify it was stored in KV
    val = mesh.get_kv(f"marker:{marker_id}")
    assert val["type"] == "work_in_progress"
    assert val["location"] == "zone_a"
    assert val["payload"]["task"] == "assembly"
    assert val["origin"] == mesh.node_id


@pytest.mark.asyncio
async def test_get_markers_by_location(mesh):
    await mesh.leave_marker("m1", "completed", "zone_a")
    await mesh.leave_marker("m2", "pending", "zone_b")

    # This might require some filtering logic
    markers = mesh.get_markers(location="zone_a")
    assert len(markers) == 1
    assert markers[0]["id"] == "m1"
