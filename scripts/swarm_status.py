import asyncio
import os
import sys
import json

sys.path.insert(0, os.path.abspath("src"))
from liminal_bridge.mesh import LiminalMesh


async def main():
    swarm_key = os.environ.get("SWARM_KEY", "KEYSTONE-POLYPHONY-UPSTREAM")
    mesh = LiminalMesh(secret_key=swarm_key)
    await mesh.start()
    try:
        await asyncio.sleep(10)  # Give it time for state sync
        backlog = mesh.get_kv("swarm_backlog") or []
        print(f"--- SWARM BACKLOG ({len(backlog)} tasks) ---")
        for task_json in backlog:
            try:
                task = json.loads(task_json)
                print(
                    f"[{task.get('status')}] {task.get('id')[:8]}: {task.get('title')} (Owner: {task.get('owner')})"
                )
            except:
                print(f"Malformed task: {task_json}")

        print("\n--- THOUGHTS ---")
        for nid, thought in mesh.thoughts.items():
            print(f"[{nid[:8]}] {thought}")

    finally:
        await mesh.stop()


if __name__ == "__main__":
    asyncio.run(main())
