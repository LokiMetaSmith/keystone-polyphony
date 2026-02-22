import pytest
import asyncio
from unittest.mock import AsyncMock, ANY
from src.liminal_bridge.mesh import LiminalMesh

@pytest.mark.asyncio
async def test_mesh_baton_local():
    """Test local baton acquisition logic."""
    mesh = LiminalMesh("test-secret")
    mesh.broadcast = AsyncMock()

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
async def test_mesh_baton_denial():
    """Test baton denial when another peer holds it."""
    mesh = LiminalMesh("test-secret")
    mesh.broadcast = AsyncMock()

    # Simulate another peer holding the lock
    mesh.batons["file.py"] = "other-peer-id"

    # Try to acquire
    success = await mesh.acquire_baton("file.py", timeout=0.1)
    assert success is False

@pytest.mark.asyncio
async def test_kv_store():
    """Test KV store updates."""
    mesh = LiminalMesh("test-secret")
    mesh.broadcast = AsyncMock()

    await mesh.update_kv("key1", "value1")
    assert mesh.get_kv("key1") == "value1"

    # Verify broadcast call using ANY for the timestamp
    mesh.broadcast.assert_called_with({
        "type": "kv_update",
        "key": "key1",
        "value": "value1"
    })
