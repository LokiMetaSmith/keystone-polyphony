import pytest
from unittest.mock import AsyncMock
from src.liminal_bridge.mesh import LiminalMesh


@pytest.fixture
def mesh():
    m = LiminalMesh("test-secret", db_path=":memory:")
    m._send_to_sidecar = AsyncMock()
    return m


@pytest.mark.asyncio
async def test_capability_advertising(mesh):
    await mesh.advertise_capabilities(["LiDAR", "UWB"])

    # Verify it was stored in KV
    val = mesh.get_kv(f"capabilities:{mesh.node_id}")
    assert "LiDAR" in val
    assert "UWB" in val


@pytest.mark.asyncio
async def test_task_picking(mesh):
    # Setup task pool in KV
    tasks = [
        {"id": "task1", "priority": 10, "status": "pending", "required": ["LiDAR"]},
        {"id": "task2", "priority": 5, "status": "pending", "required": ["Camera"]},
        {"id": "task3", "priority": 20, "status": "claimed", "required": ["LiDAR"]},
    ]
    # We use update_kv which uses LWWRegister internally
    await mesh.update_kv("task_pool", tasks)

    # Mesh has LiDAR capability
    mesh.capabilities = ["LiDAR"]

    # Should pick task1 (highest priority pending matching LiDAR)
    # task3 is already claimed.
    task = await mesh.autonomously_pick_task()
    assert task["id"] == "task1"

    # Status should be updated to 'claimed' by this node
    pool = mesh.get_kv("task_pool")
    t1 = next(t for t in pool if t["id"] == "task1")
    assert t1["status"] == "claimed"
    assert t1["claimed_by"] == mesh.node_id
