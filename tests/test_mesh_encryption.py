import pytest
from unittest.mock import AsyncMock
from src.liminal_bridge.mesh import LiminalMesh


@pytest.fixture
def mesh_node(tmp_path):
    db = tmp_path / "test.db"
    identity = tmp_path / "test.pem"
    secret = "test-secret-key-123"
    mesh = LiminalMesh(secret, db_path=str(db), identity_path=str(identity))
    mesh._send_to_sidecar = AsyncMock()
    return mesh


@pytest.mark.asyncio
async def test_encryption_key_generation(mesh_node):
    """Test that an encryption key is generated from the secret."""
    assert hasattr(mesh_node, "fernet")
    # Verify we can encrypt and decrypt with it
    msg = b"secret"
    enc = mesh_node.fernet.encrypt(msg)
    dec = mesh_node.fernet.decrypt(enc)
    assert dec == msg


@pytest.mark.asyncio
async def test_broadcast_encrypts_payload(mesh_node):
    """Test that broadcast sends an encrypted payload."""
    payload = {"type": "test_msg", "content": "hello world"}

    await mesh_node.broadcast(payload)

    mesh_node._send_to_sidecar.assert_called_once()
    call_args = mesh_node._send_to_sidecar.call_args
    msg_type, msg_payload = call_args[0]

    assert msg_type == "broadcast"
    assert "e" in msg_payload
    assert isinstance(msg_payload["e"], str)

    # Decrypt and verify content
    decrypted = mesh_node._decrypt(msg_payload["e"])
    assert decrypted["type"] == "test_msg"
    assert decrypted["content"] == "hello world"
    assert decrypted["origin"] == mesh_node.node_id
    assert "vc" in decrypted


@pytest.mark.asyncio
async def test_receive_decrypts_payload(mesh_node):
    """Test that receiving an encrypted payload decrypts it."""
    mesh_node._handle_payload = AsyncMock()

    # Create a valid encrypted payload
    original_payload = {"type": "test_msg", "content": "secret data"}
    encrypted_data = mesh_node._encrypt(original_payload)

    msg = {"type": "message", "peer_id": "some_peer", "payload": {"e": encrypted_data}}

    await mesh_node._handle_message(msg)

    mesh_node._handle_payload.assert_called_once()
    received_payload = mesh_node._handle_payload.call_args[0][0]

    assert received_payload["type"] == "test_msg"
    assert received_payload["content"] == "secret data"


@pytest.mark.asyncio
async def test_receive_unencrypted_payload_ignored_or_processed(mesh_node):
    """Test behavior for unencrypted payload (legacy support)."""
    # Assuming we still support unencrypted messages as fallback or if 'e' is missing
    mesh_node._handle_payload = AsyncMock()

    msg = {
        "type": "message",
        "peer_id": "legacy_peer",
        "payload": {"type": "test_msg", "content": "plaintext"},
    }

    await mesh_node._handle_message(msg)

    mesh_node._handle_payload.assert_called_once()
    received_payload = mesh_node._handle_payload.call_args[0][0]
    assert received_payload["content"] == "plaintext"


@pytest.mark.asyncio
async def test_decryption_failure_handling(mesh_node, capsys):
    """Test that decryption failure is handled gracefully."""
    mesh_node._handle_payload = AsyncMock()

    msg = {
        "type": "message",
        "peer_id": "bad_peer",
        "payload": {"e": "invalid_base64_or_ciphertext"},
    }

    await mesh_node._handle_message(msg)

    mesh_node._handle_payload.assert_not_called()
    captured = capsys.readouterr()
    assert "Error decrypting message" in captured.out
