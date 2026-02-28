#!/usr/bin/env python3
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
from liminal_bridge.mesh import LiminalMesh

async def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/status.py <status>")
        print("Example: python3 scripts/status.py busy")
        sys.exit(1)
        
    status = sys.argv[1]
    swarm_key = os.environ.get("SWARM_KEY", "KEYSTONE-POLYPHONY-UPSTREAM")
    
    mesh = LiminalMesh(secret_key=swarm_key)
    await mesh.start()
    
    try:
        await asyncio.sleep(2)
        await mesh.set_status(status)
        print(f"✅ Status updated to: '{status}'")
        await asyncio.sleep(2)
    finally:
        await mesh.stop()

if __name__ == "__main__":
    asyncio.run(main())
