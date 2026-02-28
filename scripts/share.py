#!/usr/bin/env python3
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
from liminal_bridge.mesh import LiminalMesh

async def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/share.py \"Your thought here\"")
        sys.exit(1)
        
    thought = " ".join(sys.argv[1:])
    swarm_key = os.environ.get("SWARM_KEY", "KEYSTONE-POLYPHONY-UPSTREAM")
    
    mesh = LiminalMesh(secret_key=swarm_key)
    
    try:
        # Wait for the mesh to initialize and connect to DHT peers
        print(">>> Warming up mesh connection...")
        await mesh.warm_up()
        
        await mesh.share_thought(thought)
        print(f"✅ Shared thought: '{thought}'")
        # Give a moment for the thought to broadcast over the DHT
        await asyncio.sleep(2)
    finally:
        await mesh.stop()

if __name__ == "__main__":
    asyncio.run(main())
