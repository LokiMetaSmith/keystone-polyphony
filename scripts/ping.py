#!/usr/bin/env python3
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
from liminal_bridge.mesh import LiminalMesh

async def main():
    if len(sys.argv) < 3:
        print("Usage: python3 scripts/ping.py <node_id> \"Your message here\"")
        sys.exit(1)
        
    target_id = sys.argv[1]
    message = " ".join(sys.argv[2:])
    swarm_key = os.environ.get("SWARM_KEY", "KEYSTONE-POLYPHONY-UPSTREAM")
    
    mesh = LiminalMesh(secret_key=swarm_key)
    
    try:
        print(">>> Warming up mesh connection...")
        await mesh.warm_up()
        
        await mesh.ping(target_id, message)
        print(f"✅ Pinged node {target_id} with message: '{message}'")
        await asyncio.sleep(2)
    finally:
        await mesh.stop()

if __name__ == "__main__":
    asyncio.run(main())
