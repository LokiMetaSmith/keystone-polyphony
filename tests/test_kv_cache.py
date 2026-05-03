import unittest
import asyncio
import json
from src.liminal_bridge.crdt import ORSet
from src.liminal_bridge.distributed_kv_cache import DistributedKVCache

class MockMesh:
    def __init__(self):
        self.node_id = "test_node_1"
        self.kv_store = {}

    async def update_set(self, key, value, urgency="low"):
        # Mocks the ORSet CRDT update behavior
        if key not in self.kv_store:
            self.kv_store[key] = ORSet()
        self.kv_store[key].add(value)

    def get_kv(self, key):
        if key in self.kv_store:
            return self.kv_store[key].value()
        return None

class TestDistributedKVCache(unittest.IsolatedAsyncioTestCase):

    async def test_collision_handling(self):
        mesh = MockMesh()
        cache = DistributedKVCache(mesh)

        # Simulate two nodes processing the exact same sequence chunk
        # and pushing the cache metadata to the CRDT
        await cache.push_cache_block("session_abc", 1, 0, "hash123")

        # Simulate node 2 doing the exact same thing (perhaps redundantly due to a network partition)
        mesh.node_id = "test_node_2"
        await cache.push_cache_block("session_abc", 1, 0, "hash456")

        # Verify both hashes exist in the ORSet and weren't destructively overwritten
        blocks = cache.get_cache_blocks("session_abc", 1)
        self.assertEqual(len(blocks), 2)

        hashes = [b["hash"] for b in blocks]
        self.assertIn("hash123", hashes)
        self.assertIn("hash456", hashes)

    async def test_metadata_reconstruction(self):
        mesh = MockMesh()
        cache = DistributedKVCache(mesh)

        # Push mock blocks out of order
        await cache.push_cache_block("session_xyz", 5, 2, "hash_seq2")
        await cache.push_cache_block("session_xyz", 5, 0, "hash_seq0")
        await cache.push_cache_block("session_xyz", 5, 1, "hash_seq1")

        # Generate the script
        script = cache.generate_pollen_fetch_script("session_xyz", "/tmp/cache")

        # Verify it reconstructs the sequence sequentially (0 -> 1 -> 2)
        lines = script.split("\n")

        # Find the pln fetch commands
        fetch_commands = [line for line in lines if line.startswith("pln fetch")]

        self.assertEqual(len(fetch_commands), 3)
        self.assertIn("hash_seq0", fetch_commands[0])
        self.assertIn("hash_seq1", fetch_commands[1])
        self.assertIn("hash_seq2", fetch_commands[2])

if __name__ == '__main__':
    unittest.main()
