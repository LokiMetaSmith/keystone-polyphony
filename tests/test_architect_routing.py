import unittest
import asyncio
import os
from src.liminal_bridge.architect import Architect
from src.liminal_bridge.mesh import LiminalMesh

class TestArchitectRouting(unittest.IsolatedAsyncioTestCase):

    def test_provider_heuristics(self):
        # Override the env variable dynamically
        original_model = os.environ.get("DUCKY_MODEL")
        os.environ["DUCKY_MODEL"] = "pollen:test-llama-model"

        # Instantiate Architect
        architect = Architect()

        # Verify it bypasses OpenAI/Anthropic and selects the local pollen mesh
        self.assertEqual(architect.provider, "pollen_mesh")
        self.assertEqual(architect.model, "test-llama-model")

        # Cleanup
        if original_model is None:
            del os.environ["DUCKY_MODEL"]
        else:
            os.environ["DUCKY_MODEL"] = original_model

    async def test_hardware_capability_filtering(self):
        # We don't want to start the sidecar for a unit test
        class OfflineMesh(LiminalMesh):
            async def _send_to_sidecar(self, msg_type, payload):
                pass

        # Initialize Node 1 (Has GPU)
        mesh1 = OfflineMesh(secret_key="test", db_path=":memory:")
        mesh1.node_id = "node1"
        mesh1.capabilities = ["seed", "compute", "role=gpu"]

        # Initialize Node 2 (No GPU)
        mesh2 = OfflineMesh(secret_key="test", db_path=":memory:")
        mesh2.node_id = "node2"
        mesh2.capabilities = ["seed", "compute"]

        # Callbacks to verify routing
        node1_called = False
        node2_called = False

        async def cb1(origin, cmd):
            nonlocal node1_called
            node1_called = True

        async def cb2(origin, cmd):
            nonlocal node2_called
            node2_called = True

        mesh1.on_command_request = cb1
        mesh2.on_command_request = cb2

        # The command requested explicitly requires a GPU
        payload = {
            "type": "command_request",
            "command": {"type": "run_inference", "prompt": "test"},
            "capabilities": ["role=gpu"],
            "target": None,
            "origin": "sender_node"
        }

        # Inject the payload directly into both nodes' handler
        await mesh1._handle_payload(payload)
        await mesh2._handle_payload(payload)

        # Wait a tiny bit for the async task to trigger
        await asyncio.sleep(0.01)

        # Assert that only Node 1 (which has the required tag) fired the callback
        self.assertTrue(node1_called)
        self.assertFalse(node2_called)

if __name__ == '__main__':
    unittest.main()
