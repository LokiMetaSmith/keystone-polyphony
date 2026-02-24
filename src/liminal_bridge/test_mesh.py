import pytest
from unittest.mock import AsyncMock
from src.liminal_bridge.mesh import LiminalMesh


@pytest.fixture
def mesh(tmp_path):
    """Fixture to create a LiminalMesh with temporary DB and Identity."""
    db = tmp_path / "test.db"
    identity = tmp_path / "test.pem"
    mesh = LiminalMesh("test-secret", db_path=str(db), identity_path=str(identity))
    mesh.broadcast = AsyncMock()
    yield mesh
    # Cleanup is handled by tmp_path, but stop() closes DB connection
    # Since we don't start() the mesh in these unit tests, stop() isn't strictly needed for process
    # but good to close DB connection if needed.
    if mesh.conn:
        mesh.conn.close()


@pytest.mark.asyncio
async def test_mesh_baton_local(mesh):
    """Test local baton acquisition logic."""
    # Acquire new baton
    success = await mesh.acquire_baton("file.py", timeout=0.1)
    assert success is True
    assert mesh.batons["file.py"] == mesh.node_id

    # Re-acquire same baton (idempotent)
    success = await mesh.acquire_baton("file.py", timeout=0.1)
    assert success is True

    # Release baton
    await mesh.release_baton("file.py")
    assert "file.py" not in mesh.batons


@pytest.mark.asyncio
async def test_mesh_baton_denial(mesh):
    """Test baton denial when another peer holds it."""
    # Simulate another peer holding the lock
    mesh.batons["file.py"] = "other-peer-id"

    # Try to acquire
    success = await mesh.acquire_baton("file.py", timeout=0.1)
    assert success is False


@pytest.mark.asyncio
async def test_kv_store(mesh):
    """Test KV store updates."""
    await mesh.update_kv("key1", "value1")
    assert mesh.get_kv("key1") == "value1"

    # Verify broadcast call using ANY for the timestamp
    mesh.broadcast.assert_called_with(
        {"type": "kv_update", "key": "key1", "value": "value1"}
    )
