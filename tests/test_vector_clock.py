import pytest
from unittest.mock import AsyncMock
from src.liminal_bridge.mesh import LiminalMesh


@pytest.fixture
def mesh_a(tmp_path):
    db = tmp_path / "a.db"
    identity = tmp_path / "a.pem"
    mesh = LiminalMesh("test-secret", db_path=str(db), identity_path=str(identity))
    mesh.broadcast = AsyncMock()
    return mesh


@pytest.fixture
def mesh_b(tmp_path):
    db = tmp_path / "b.db"
    identity = tmp_path / "b.pem"
    mesh = LiminalMesh("test-secret", db_path=str(db), identity_path=str(identity))
    mesh.broadcast = AsyncMock()
    return mesh


@pytest.mark.asyncio
async def test_vector_clock_initialization(mesh_a):
    """Test that vector clock is initialized correctly."""
    assert isinstance(mesh_a.vector_clock, dict)
    assert mesh_a.vector_clock[mesh_a.node_id] == 0


@pytest.mark.asyncio
async def test_vector_clock_update_kv(mesh_a):
    """Test that updating KV increments the clock."""
    initial_clock = mesh_a.vector_clock[mesh_a.node_id]
    await mesh_a.update_kv("key1", "value1")
    assert mesh_a.vector_clock[mesh_a.node_id] == initial_clock + 1

    # Verify the broadcast payload contains the vector clock (inside crdt or top level)
    call_args = mesh_a.broadcast.call_args[0][0]
    # In new CRDT implementation, vc is inside crdt dict
    if "crdt" in call_args:
        assert "vc" in call_args["crdt"]
        assert call_args["crdt"]["vc"] == mesh_a.vector_clock
    else:
        assert "vc" in call_args
        assert call_args["vc"] == mesh_a.vector_clock


@pytest.mark.asyncio
async def test_receive_update_respects_causality(mesh_a, mesh_b):
    """Test that receiving an update respects causal ordering."""
    # Mesh A updates key1
    await mesh_a.update_kv("key1", "value_a")

    # Mesh B receives the update
    # Simulate network transmission (add origin, etc if needed, but _handle_payload does some of this)
    # The payload from broadcast already has origin/timestamp added in broadcast() normally,
    # but since we mocked broadcast, we need to manually reconstruct what would be sent.
    # Actually broadcast calls _send_to_sidecar, which just sends json.
    # mesh.broadcast() adds origin, timestamp, sender_pubkey.

    # Let's manually construct the message Mesh B receives
    msg_from_a = {
        "type": "kv_update",
        "key": "key1",
        "value": "value_a",
        "origin": mesh_a.node_id,
        "vc": mesh_a.vector_clock,
        "timestamp": 1000,
    }

    await mesh_b._handle_payload(msg_from_a)
    assert mesh_b.get_kv("key1") == "value_a"
    # B's clock should have merged A's clock
    assert mesh_b.vector_clock[mesh_a.node_id] == mesh_a.vector_clock[mesh_a.node_id]

    # Now let's simulate a concurrent update or a stale update
    # Scenario: A sends another update, but it arrives late (stale).
    # But first A needs to update again to have a "later" state.
    await mesh_a.update_kv("key1", "value_a_2")
    msg_from_a_2 = {
        "type": "kv_update",
        "key": "key1",
        "value": "value_a_2",
        "origin": mesh_a.node_id,
        "vc": mesh_a.vector_clock,  # This is the new clock
        "timestamp": 1001,
    }

    # Apply the second update
    await mesh_b._handle_payload(msg_from_a_2)
    assert mesh_b.get_kv("key1") == "value_a_2"

    # Now try to apply the OLD update (msg_from_a) again
    await mesh_b._handle_payload(msg_from_a)
    # Should still be the new value
    assert mesh_b.get_kv("key1") == "value_a_2"


@pytest.mark.asyncio
async def test_concurrent_writes(mesh_a, mesh_b):
    """Test resolution of concurrent writes."""
    # A and B both start at {A:0, B:0} implicitly

    # A updates key1
    # We need to manually manipulate clocks to simulate concurrency if we don't have a real network

    # A increments: {A:1, B:0}
    mesh_a.vector_clock[mesh_a.node_id] += 1
    vc_a = mesh_a.vector_clock.copy()

    # B increments: {A:0, B:1}
    mesh_b.vector_clock[mesh_b.node_id] += 1
    vc_b = mesh_b.vector_clock.copy()

    # Both try to update key1
    msg_a = {
        "type": "kv_update",
        "key": "concurrent",
        "value": "val_a",
        "origin": mesh_a.node_id,
        "vc": vc_a,
        "timestamp": 1000,
    }

    msg_b = {
        "type": "kv_update",
        "key": "concurrent",
        "value": "val_b",
        "origin": mesh_b.node_id,
        "vc": vc_b,
        "timestamp": 1000,  # Same timestamp to test tie-breaker
    }

    # Mesh B receives msg_a
    await mesh_b._handle_payload(msg_a)

    # Now Mesh B receives msg_b (which is effectively a local update it just made, or from another node C)
    # But wait, we are testing how ONE node resolves conflict.
    # Let's say Mesh C receives both.

    mesh_c = LiminalMesh("test-secret", db_path=":memory:", identity_path="c.pem")

    # C receives A
    await mesh_c._handle_payload(msg_a)
    assert mesh_c.get_kv("concurrent") == "val_a"

    # C receives B. VC_A {A:1} and VC_B {B:1} are concurrent.
    # Logic should fall back to timestamp. Timestamps are equal.
    # Logic should fall back to node_id.
    # If "val_b" > "val_a" or node_id B > node_id A?
    # Let's assume we use node_id as tie breaker.

    await mesh_c._handle_payload(msg_b)

    val_c = mesh_c.get_kv("concurrent")

    # We need to know which node_id is greater to assert
    if mesh_b.node_id > mesh_a.node_id:
        assert val_c == "val_b"
    else:
        assert val_c == "val_a"


@pytest.mark.asyncio
async def test_get_all_kv_unwraps_values(mesh_a):
    """Test that get_all_kv returns unwrapped values."""
    await mesh_a.update_kv("key1", "value1")
    await mesh_a.update_kv("key2", "value2")

    all_kv = mesh_a.get_all_kv()
    assert all_kv["key1"] == "value1"
    assert all_kv["key2"] == "value2"
    assert "vc" not in all_kv["key1"]
