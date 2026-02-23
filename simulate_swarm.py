import asyncio
import os
import sys

# Ensure we can import local modules
sys.path.append(os.path.abspath("src"))

from liminal_bridge.mesh import LiminalMesh

async def run_sim_agent(name: str, secret: str, behavior: list):
    """Simulates a single Jules agent interacting with the mesh."""
    print(f"[{name}] Booting...")

    # Each agent needs its own mesh instance
    mesh = LiminalMesh(secret_key=secret)
    await mesh.start()

    # Wait for connection & discovery
    await asyncio.sleep(2)
    print(f"[{name}] Connected (Node ID: {mesh.node_id})")

    for step_delay, action, arg in behavior:
        await asyncio.sleep(step_delay)

        if action == "share":
            await mesh.share_thought(arg)
            print(f"[{name}] Shared thought: '{arg}'")

        elif action == "acquire":
            print(f"[{name}] Attempting to acquire baton for {arg}...")
            success = await mesh.acquire_baton(arg, timeout=2.0)
            status = "SUCCESS" if success else "FAILED"
            print(f"[{name}] Acquire {arg}: {status}")

        elif action == "release":
            await mesh.release_baton(arg)
            print(f"[{name}] Released baton for {arg}")

        elif action == "peek":
            # Print what this agent sees from others
            thoughts = mesh.thoughts
            print(f"[{name}] Current Swarm Thoughts: {len(thoughts)} items")
            for origin, content in thoughts.items():
                if origin != mesh.node_id:
                    print(f"   -> Peer {origin[:6]}: {content}")

    # Keep alive briefly to receive final messages
    await asyncio.sleep(2)
    await mesh.stop()
    print(f"[{name}] Shutdown.")

async def main():
    secret = "simulation-secret-123"

    # Agent 1: The "Senior Dev" who locks the file first
    agent1_behavior = [
        (1.0, "share", "Refactoring auth module"),
        (0.5, "acquire", "src/auth.py"),  # T=1.5s: Should succeed
        (3.0, "release", "src/auth.py"),  # T=4.5s: Release
    ]

    # Agent 2: The "Junior Dev" who tries to edit the same file
    agent2_behavior = [
        (1.0, "share", "Writing tests for auth"),
        (1.5, "acquire", "src/auth.py"),  # T=2.5s: Should fail (locked by Agent 1)
        (3.0, "acquire", "src/auth.py"),  # T=5.5s: Should succeed (after Agent 1 releases)
        (1.0, "peek", None)
    ]

    # Run them concurrently
    await asyncio.gather(
        run_sim_agent("Agent-1", secret, agent1_behavior),
        run_sim_agent("Agent-2", secret, agent2_behavior)
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
