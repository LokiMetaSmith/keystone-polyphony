import asyncio
import os
import sys
import json
import time

sys.path.insert(0, os.path.abspath("src"))
from liminal_bridge.mesh import LiminalMesh


async def main():
    swarm_key = os.environ.get("SWARM_KEY", "KEYSTONE-POLYPHONY-UPSTREAM")
    mesh = LiminalMesh(secret_key=swarm_key, capabilities=["worker", "executor"])

    # Callback for commands
    async def on_command(origin, command):
        print(f">>> [Worker] RECEIVED COMMAND from {origin}: {command}")
        payload = command.get("payload", "")

        # Simulate work
        await mesh.set_status("busy")
        await mesh.share_thought(f"Executing command: {payload}")

        # Here you would actually execute the payload
        # For this demo, we just wait
        await asyncio.sleep(5)

        await mesh.share_thought(f"Finished executing: {payload}")
        await mesh.set_status("idle")

    mesh.on_command_request = on_command

    await mesh.start()
    try:
        await mesh.set_status("idle")
        print(f">>> [Worker] Node {mesh.node_id} is IDLE and listening for commands...")

        # Keep running
        while True:
            await asyncio.sleep(1)
    finally:
        await mesh.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
