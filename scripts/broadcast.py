#!/usr/bin/env python3
import asyncio
import os
import sys
import json

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
)
from liminal_bridge.mesh import LiminalMesh


async def main():
    if len(sys.argv) < 2:
        print(
            "Usage: python3 scripts/broadcast.py <command> [target] [capabilities] [status_filter]"
        )
        print('Example: python3 scripts/broadcast.py "Run tests" "" "tester" "idle"')
        sys.exit(1)

    command = sys.argv[1]
    target = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else None
    caps = sys.argv[3].split(",") if len(sys.argv) > 3 and sys.argv[3] else []
    status_filter = sys.argv[4] if len(sys.argv) > 4 else None

    swarm_key = os.environ.get("SWARM_KEY", "KEYSTONE-POLYPHONY-UPSTREAM")
    mesh = LiminalMesh(secret_key=swarm_key)

    try:
        print(">>> Connecting to swarm...")
        await mesh.start()
        await asyncio.sleep(5)  # Give time for discovery

        cmd_obj = {"type": "execute", "payload": command}
        await mesh.broadcast_command(
            cmd_obj, target=target, capabilities=caps, status_filter=status_filter
        )
        print(f"✅ Broadcasted command: '{command}'")
        await asyncio.sleep(2)
    finally:
        await mesh.stop()


if __name__ == "__main__":
    asyncio.run(main())
