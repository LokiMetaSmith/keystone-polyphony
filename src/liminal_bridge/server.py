import asyncio
import os
import sys
import argparse
import time

# Get the directory containing this script
current_dir = os.path.dirname(os.path.abspath(__file__))
# Add it to sys.path so we can import 'mesh', 'architect', 'pulse'
sys.path.append(current_dir)

# Handle both relative and absolute imports
try:
    from .mesh import LiminalMesh
    from .architect import Architect
    from .pulse import Pulse
except ImportError:
    from mesh import LiminalMesh
    from architect import Architect
    from pulse import Pulse

from mcp.server.fastmcp import FastMCP

# Initialize components
SWARM_KEY = os.getenv("SWARM_KEY", "liminal-default-secret")
mesh = LiminalMesh(secret_key=SWARM_KEY)
architect = Architect()
pulse = Pulse(mesh, architect)

# Create MCP Server
mcp = FastMCP("Keystone-Polyphony")

# --- MCP Tools ---
@mcp.tool()
async def register_to_swarm(github_secret: str = None) -> str:
    """Initializes the connection to the P2P swarm."""
    global mesh, pulse
    if github_secret:
        if mesh.secret_key != github_secret:
            if mesh.running:
                await mesh.stop()
            mesh = LiminalMesh(secret_key=github_secret)
            pulse = Pulse(mesh, architect)

    if not mesh.running:
        await mesh.start()
    return f"Connected to Liminal Swarm. Node ID: {mesh.node_id}. Topic: {mesh.topic[:8]}..."

@mcp.tool()
async def share_thought(thought: str) -> str:
    """Broadcasts a 'thought'."""
    if not mesh.running: await mesh.start()
    await mesh.share_thought(thought)
    return "Thought streamed."

@mcp.tool()
async def acquire_baton(file_path: str) -> str:
    """Acquires an exclusive lock on a file."""
    if not mesh.running: await mesh.start()
    success = await mesh.acquire_baton(file_path)
    if success:
        return f"SUCCESS: Baton acquired for {file_path}."
    else:
        owner = mesh.batons.get(file_path, "unknown")
        return f"DENIED: {file_path} is currently locked by {owner}."

@mcp.tool()
async def release_baton(file_path: str) -> str:
    """Releases the lock on a file."""
    if not mesh.running: await mesh.start()
    await mesh.release_baton(file_path)
    await pulse.on_baton_release(file_path)
    return f"Baton released for {file_path}."

@mcp.tool()
async def peek_liminal(key: str = None) -> str:
    """Reads the shared state."""
    if key:
        val = mesh.get_kv(key)
        return str(val) if val else "Key not found."
    return str({"thoughts": mesh.thoughts, "batons": mesh.batons, "kv": mesh.kv_store})

@mcp.tool()
async def consult_architect(context: str) -> str:
    """Manually triggers the Architect."""
    if not mesh.running: await mesh.start()
    await pulse.trigger(context=f"manual:{context}")
    plan = mesh.get_kv("master_plan")
    return f"Architect consulted. Plan: {plan}"

# --- Seed Mode ---
async def run_seed_mode(timeout: int = None):
    """Runs the mesh in seed mode (no MCP server)."""
    print(f"Starting Liminal Swarm Seed Node (Key: {SWARM_KEY[:8]}...)...")
    await mesh.start()

    start_time = time.time()
    try:
        while True:
            await asyncio.sleep(1)

            # Check timeout
            if timeout and (time.time() - start_time > timeout):
                print(f"Seed node timeout reached ({timeout}s).")
                break

            # Periodically pulse (every 60s check, but trigger respects cooldown)
            if int(time.time()) % 60 == 0:
                await pulse.trigger(context="seed_heartbeat")

    except asyncio.CancelledError:
        pass
    finally:
        print("Stopping seed node...")
        await mesh.stop()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["mcp", "seed"], default="mcp", help="Run mode: 'mcp' server or 'seed' node")
    parser.add_argument("--timeout", type=int, default=None, help="Timeout in seconds for seed mode")

    # FastMCP uses click/typer which might grab args, so we use parse_known_args
    args, unknown = parser.parse_known_args()

    if args.mode == "seed":
        try:
            asyncio.run(run_seed_mode(args.timeout))
        except KeyboardInterrupt:
            pass
    else:
        # Clean up argv for FastMCP
        sys.argv = [sys.argv[0]] + unknown
        mcp.run()
