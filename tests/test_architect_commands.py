import asyncio
import os
import sys
import json
import tempfile
import shutil
from unittest.mock import AsyncMock, patch

# Ensure we can import local modules
sys.path.append(os.path.abspath("src"))

from liminal_bridge.mesh import LiminalMesh
from liminal_bridge.pulse import Pulse
from liminal_bridge.architect import Architect


async def _run_pulse_broadcasts_architect_commands():
    print(">>> Starting Architect Command Test...")
    tmp_dir = tempfile.mkdtemp()
    swarm_key = "test-swarm-key"

    try:
        # Node 1: The Coordinator
        node1 = LiminalMesh(
            secret_key=swarm_key,
            db_path=os.path.join(tmp_dir, "node1.db"),
            identity_path=os.path.join(tmp_dir, "node1.pem"),
        )

        # Mock Architect to return a plan with commands
        mock_architect = Architect()
        mock_architect.consult = AsyncMock()
        mock_architect.consult.return_value = json.dumps(
            {
                "backlog": ["task-1"],
                "commands": [
                    {
                        "target": "target-node-id",
                        "command": "reproduce bug",
                        "capabilities": ["tester"],
                    }
                ],
            }
        )

        pulse = Pulse(node1, mock_architect)
        node1.on_baton_release = pulse.on_baton_release

        # Track command_request messages sent by node1
        sent_commands = []

        async def mock_broadcast(payload, urgency="low"):
            if payload.get("type") == "command_request":
                sent_commands.append(payload)
            # Use real broadcast logic but skip sidecar for simplicity in this unit-ish test
            pass

        with patch.object(node1, "broadcast", new=mock_broadcast):
            await pulse.trigger(context="force")

            # Check if broadcast_command was called via the mock_broadcast
            assert (
                sent_commands
            ), "FAILURE: Pulse did not broadcast command from Architect."

            cmd = sent_commands[0]
            assert cmd["target"] == "target-node-id"
            assert cmd["command"]["payload"] == "reproduce bug"
            assert cmd["capabilities"] == ["tester"]

            print("SUCCESS: Pulse correctly broadcasted Architect's command!")

    finally:
        shutil.rmtree(tmp_dir)


def test_pulse_broadcasts_architect_commands():
    asyncio.run(_run_pulse_broadcasts_architect_commands())


if __name__ == "__main__":
    asyncio.run(_run_pulse_broadcasts_architect_commands())
