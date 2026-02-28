import asyncio
import json
import os
import sys
import pytest

# Ensure we can import local modules
sys.path.append(os.path.abspath("src"))

from liminal_bridge.mesh import LiminalMesh  # noqa: E402


@pytest.mark.asyncio
async def test_chat():
    print("Testing Ensemble Chat...")

    # Setup Node 1
    mesh1 = LiminalMesh(
        "chat-test-secret", db_path="chat1.db", identity_path="chat1.pem"
    )
    await mesh1.start()

    # Setup Node 2
    mesh2 = LiminalMesh(
        "chat-test-secret", db_path="chat2.db", identity_path="chat2.pem"
    )
    await mesh2.start()

    # Wait for connection
    print("Waiting for discovery...")
    for i in range(10):
        if len(mesh1.peers) > 0 and len(mesh2.peers) > 0:
            break
        await asyncio.sleep(1)

    if len(mesh1.peers) == 0:
        print("FAILURE: Peers did not discover each other.")
        await mesh1.stop()
        await mesh2.stop()
        return

    # Post message from Node 1
    topic = "test-topic"
    msg1 = {"sender": mesh1.node_id, "timestamp": 100.0, "content": "Message from 1"}
    await mesh1.update_set(f"chat:{topic}", json.dumps(msg1))

    # Post message from Node 2
    msg2 = {"sender": mesh2.node_id, "timestamp": 200.0, "content": "Message from 2"}
    await mesh2.update_set(f"chat:{topic}", json.dumps(msg2))

    # Wait for sync
    print("Waiting for sync...")
    await asyncio.sleep(2)

    # Read from Node 1
    res1 = mesh1.get_kv(f"chat:{topic}")
    print(f"Node 1 sees: {res1}")

    # Read from Node 2
    res2 = mesh2.get_kv(f"chat:{topic}")
    print(f"Node 2 sees: {res2}")

    if len(res1) == 2 and len(res2) == 2:
        print("SUCCESS: Chat messages synced correctly across members of the swarm!")
    else:
        print(
            f"FAILURE: Sync incomplete. Node 1 size: {len(res1)}, Node 2 size: {len(res2)}"
        )

    await mesh1.stop()
    await mesh2.stop()

    # Cleanup
    for f in ["chat1.db", "chat2.db", "chat1.pem", "chat2.pem"]:
        if os.path.exists(f):
            os.remove(f)


if __name__ == "__main__":
    asyncio.run(test_chat())
