import asyncio
import os
import sys
import json
import pytest
import shutil
import tempfile

# Ensure we can import local modules
sys.path.insert(0, os.path.abspath("src"))

from liminal_bridge.mesh import LiminalMesh
from liminal_bridge.storage import SQLiteStorageProvider


@pytest.mark.asyncio
async def test_unread_tracking():
    # Setup temp dirs
    tmp_dir = tempfile.mkdtemp()
    db1 = os.path.join(tmp_dir, "db1.db")
    id1 = os.path.join(tmp_dir, "id1.pem")

    mesh = LiminalMesh(
        secret_key="test-key",
        storage_provider=SQLiteStorageProvider(db1),
        identity_path=id1,
    )

    try:
        await mesh.start()

        # 1. Post messages to two topics
        await mesh.update_set(
            "chat:general",
            json.dumps({"sender": "bot", "timestamp": 100, "content": "hi"}),
        )
        await mesh.update_set(
            "chat:work",
            json.dumps({"sender": "bot", "timestamp": 200, "content": "work"}),
        )

        # 2. Check unread - both should be unread (no read_ts metadata)
        unread = []
        for key in mesh.kv_store.keys():
            if key.startswith("chat:"):
                topic = key[5:]
                meta_val = mesh.storage.get_metadata(f"read_ts:{topic}")
                read_ts = float(meta_val) if meta_val else 0

                has_new = False
                messages_raw = mesh.get_kv(key) or []
                for m_json in messages_raw:
                    if json.loads(m_json).get("timestamp", 0) > read_ts:
                        has_new = True
                        break
                if has_new:
                    unread.append(topic)

        assert "general" in unread
        assert "work" in unread

        # 3. Mark general as read
        # Simulating mark_chat_read tool logic
        last_msg = 100
        mesh.storage.save_metadata("read_ts:general", str(last_msg))

        # 4. Check unread again - only work should be unread
        unread = []
        for key in mesh.kv_store.keys():
            if key.startswith("chat:"):
                topic = key[5:]
                meta_val = mesh.storage.get_metadata(f"read_ts:{topic}")
                read_ts = float(meta_val) if meta_val else 0

                has_new = False
                messages_raw = mesh.get_kv(key) or []
                for m_json in messages_raw:
                    if json.loads(m_json).get("timestamp", 0) > read_ts:
                        has_new = True
                        break
                if has_new:
                    unread.append(topic)

        assert "general" not in unread
        assert "work" in unread

        # 5. Add a NEW message to general
        await mesh.update_set(
            "chat:general",
            json.dumps({"sender": "bot", "timestamp": 150, "content": "new hi"}),
        )

        # 6. Check unread again - both should be unread now
        unread = []
        for key in mesh.kv_store.keys():
            if key.startswith("chat:"):
                topic = key[5:]
                meta_val = mesh.storage.get_metadata(f"read_ts:{topic}")
                read_ts = float(meta_val) if meta_val else 0

                has_new = False
                messages_raw = mesh.get_kv(key) or []
                for m_json in messages_raw:
                    if json.loads(m_json).get("timestamp", 0) > read_ts:
                        has_new = True
                        break
                if has_new:
                    unread.append(topic)

        assert "general" in unread
        assert "work" in unread

    finally:
        await mesh.stop()
        shutil.rmtree(tmp_dir)


if __name__ == "__main__":
    asyncio.run(test_unread_tracking())
