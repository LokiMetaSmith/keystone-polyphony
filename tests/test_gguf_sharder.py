import unittest
import os
import json
import hashlib
from src.liminal_bridge.gguf_sharder import GGUFSharder
from src.liminal_bridge.gguf_distributor import ModelDistributor

class TestGGUFShardingAndChunking(unittest.TestCase):

    def setUp(self):
        # We will mock the tensor reading inside GGUFSharder for 33 layers
        self.sharder = GGUFSharder("mock.gguf")
        # Override the mocked tensors to exactly 33 layers for the test
        tensors = []
        for layer in range(33):
            tensors.append({"name": f"blk.{layer}.attn_q.weight", "size_bytes": 100})
        tensors.append({"name": "token_embd.weight", "size_bytes": 100})
        tensors.append({"name": "output.weight", "size_bytes": 100})
        self.sharder._tensors = tensors

    def test_pipeline_math_verification(self):
        # 33 layers into 4 stages: 33/4 = 8 remainder 1.
        # Stages should have: 9, 8, 8, 8 layers.
        stages = self.sharder.calculate_pipeline_stages(4)

        self.assertEqual(len(stages), 4)
        self.assertEqual(stages[0]["num_layers"], 9)
        self.assertEqual(stages[1]["num_layers"], 8)
        self.assertEqual(stages[2]["num_layers"], 8)
        self.assertEqual(stages[3]["num_layers"], 8)

        # Verify layer ranges don't overlap
        self.assertEqual(stages[0]["layer_start"], 0)
        self.assertEqual(stages[0]["layer_end"], 8)
        self.assertEqual(stages[1]["layer_start"], 9)
        self.assertEqual(stages[1]["layer_end"], 16)

    def test_tag_generation(self):
        stages = self.sharder.calculate_pipeline_stages(4)

        # First stage needs embeddings, final needs output
        self.assertTrue(stages[0]["requires_embeddings"])
        self.assertFalse(stages[0]["requires_output_head"])

        self.assertFalse(stages[3]["requires_embeddings"])
        self.assertTrue(stages[3]["requires_output_head"])

    def test_manifest_determinism(self):
        distributor = ModelDistributor(chunk_size_mb=1) # small chunk size
        output_dir = "/tmp/test_pollen_dist"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        test_file = "/tmp/test_pollen_dist/static_test.bin"
        static_data = b"HelloPollenMesh" * 1024 # Create a static payload

        with open(test_file, "wb") as f:
            f.write(static_data)

        chunks = distributor.chunk_file(test_file, output_dir)

        # Verify the hash is exactly the same every time for this static data
        first_chunk_hash = hashlib.sha256(static_data[:distributor.chunk_size_bytes]).hexdigest()
        self.assertEqual(chunks[0]["hash"], first_chunk_hash)

        manifest_path = os.path.join(output_dir, "manifest.json")
        manifest = distributor.generate_distribution_manifest("test", chunks, manifest_path)

        with open(manifest_path, "r") as f:
            loaded_manifest = json.load(f)

        self.assertEqual(loaded_manifest["chunks"][0]["hash"], first_chunk_hash)

        # Cleanup
        os.remove(test_file)
        os.remove(manifest_path)
        for c in chunks:
            os.remove(c["path"])

if __name__ == '__main__':
    unittest.main()
