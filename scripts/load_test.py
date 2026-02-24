import asyncio
import os
import sys
import random
import time
import argparse
from typing import List

# Ensure we can import local modules
sys.path.append(os.path.abspath("src"))

from liminal_bridge.mesh import LiminalMesh  # noqa: E402


class LoadTestAgent:
    def __init__(self, name: str, secret: str, db_path: str, identity_path: str):
        self.name = name
        self.mesh = LiminalMesh(
            secret_key=secret, db_path=db_path, identity_path=identity_path
        )
        self.actions_performed = 0
        self.errors = 0

    async def start(self):
        try:
            await self.mesh.start()
        except Exception as e:
            print(f"[{self.name}] Failed to start: {e}")
            self.errors += 1

    async def stop(self):
        try:
            await self.mesh.stop()
        except Exception as e:
            print(f"[{self.name}] Failed to stop: {e}")
            self.errors += 1

    async def run(self, duration: int):
        end_time = time.time() + duration
        while time.time() < end_time:
            try:
                action = random.choice(["share", "kv_update", "baton"])
                if action == "share":
                    await self.mesh.share_thought(
                        f"Hello from {self.name} at {time.time()}"
                    )
                elif action == "kv_update":
                    key = f"key-{random.randint(0, 10)}"
                    value = f"value-{random.randint(0, 100)}"
                    await self.mesh.update_kv(key, value)
                elif action == "baton":
                    resource = f"res-{random.randint(0, 5)}"
                    if await self.mesh.acquire_baton(resource, timeout=1.0):
                        await asyncio.sleep(random.uniform(0.1, 0.5))
                        await self.mesh.release_baton(resource)

                self.actions_performed += 1
                await asyncio.sleep(random.uniform(0.5, 2.0))
            except Exception as e:
                print(f"[{self.name}] Error in run loop: {e}")
                self.errors += 1


async def main():
    parser = argparse.ArgumentParser(description="Load test for LiminalMesh")
    parser.add_argument("--agents", type=int, default=5, help="Number of agents")
    parser.add_argument("--duration", type=int, default=30, help="Duration in seconds")
    args = parser.parse_args()

    secret = "load-test-secret"
    agents: List[LoadTestAgent] = []

    # Create agents
    for i in range(args.agents):
        name = f"Agent-{i}"
        db_path = f"agent{i}.db"
        id_path = f"agent{i}.pem"
        # Cleanup previous run
        if os.path.exists(db_path):
            os.remove(db_path)
        if os.path.exists(id_path):
            os.remove(id_path)

        agents.append(LoadTestAgent(name, secret, db_path, id_path))

    # Start agents
    print(f"Starting {len(agents)} agents for {args.duration} seconds...")
    await asyncio.gather(*(a.start() for a in agents))

    # Wait for discovery
    print("Waiting for discovery...")
    await asyncio.sleep(5)

    # Run load test
    print("Running load test...")
    await asyncio.gather(*(a.run(args.duration) for a in agents))

    # Stop agents
    print("Stopping agents...")
    await asyncio.gather(*(a.stop() for a in agents))

    # Report
    total_actions = sum(a.actions_performed for a in agents)
    total_errors = sum(a.errors for a in agents)
    print(f"Total actions: {total_actions}")
    print(f"Total errors: {total_errors}")

    # Cleanup
    for i in range(args.agents):
        db_path = f"agent{i}.db"
        id_path = f"agent{i}.pem"
        if os.path.exists(db_path):
            os.remove(db_path)
        if os.path.exists(id_path):
            os.remove(id_path)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
