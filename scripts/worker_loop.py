import asyncio
import os
import sys
import json
import time

sys.path.insert(0, os.path.abspath("src"))
from liminal_bridge.mesh import LiminalMesh
from liminal_bridge.auth import get_or_create_swarm_key
from core.collaboration import FencedLedger, EnsembleConductor


async def main():
    swarm_key = get_or_create_swarm_key()
    mesh = LiminalMesh(secret_key=swarm_key, capabilities=["worker", "executor"])
    collab_db = os.getenv("LIMINAL_COLLAB_DB", "collab_ledger.db")
    ledger = FencedLedger(collab_db)
    conductor = EnsembleConductor(ledger)

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
        last_eval_time = 0.0
        while True:
            # Autonomous conductor evaluation every 15s if idle
            if time.time() - last_eval_time > 15.0:
                last_eval_time = time.time()
                try:
                    eval_res = conductor.evaluate_and_act(mesh.node_id)
                    if eval_res["claimed_lease"]:
                        print(
                            f">>> [Conductor] Node {mesh.node_id} claimed singleton Conductor podium (fence: {eval_res['fence_token']})"
                        )
                    if eval_res["emitted_signals"]:
                        print(
                            f">>> [Conductor] Node {mesh.node_id} emitted host signals: {eval_res['emitted_signals']}"
                        )
                except Exception:
                    pass
            await asyncio.sleep(1)
    finally:
        await mesh.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
