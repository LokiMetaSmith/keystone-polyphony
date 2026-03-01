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
    import json

    # Setup task pool in KV
    tasks = [
        json.dumps(
            {"id": "task1", "priority": "high", "status": "todo", "required": ["LiDAR"]}
        ),
        json.dumps(
            {"id": "task2", "priority": "low", "status": "todo", "required": ["Camera"]}
        ),
        json.dumps(
            {
                "id": "task3",
                "priority": "high",
                "status": "claimed",
                "required": ["LiDAR"],
            }
        ),
    ]
    # We use update_set which uses ORSet internally
    for task in tasks:
        await mesh.update_set("swarm_backlog", task)

    # Mesh has LiDAR capability
    mesh.capabilities = ["LiDAR"]

    # Should pick task1 (highest priority pending matching LiDAR)
    # task3 is already claimed.
    task = await mesh.autonomously_pick_task()
    assert task["id"] == "task1"

    # Status should be updated to 'in_progress' by this node
    pool = mesh.get_kv("swarm_backlog")
    t1 = next(json.loads(t) for t in pool if json.loads(t)["id"] == "task1")
    assert t1["status"] == "in_progress"
    assert t1["owner"] == mesh.node_id
