import asyncio
import os
import sys

# Get the directory containing this script
current_dir = os.path.dirname(os.path.abspath(__file__))
# Add it to sys.path so we can import 'mesh', 'architect', 'pulse'
sys.path.append(current_dir)

from mcp.server.fastmcp import FastMCP
from mesh import LiminalMesh
from architect import Architect
from pulse import Pulse

# Initialize components
SWARM_KEY = os.getenv("SWARM_KEY", "liminal-default-secret")
mesh = LiminalMesh(secret_key=SWARM_KEY)
architect = Architect()
pulse = Pulse(mesh, architect)

# Create MCP Server
mcp = FastMCP("Keystone-Polyphony")

@mcp.tool()
async def register_to_swarm(github_secret: str = None) -> str:
    """
    Initializes the connection to the P2P swarm.
    """
    if github_secret:
        # If key changes, we need to restart the mesh
        if mesh.secret_key != github_secret:
            if mesh.running:
                await mesh.stop()
            # Re-initialize properly
            global mesh, pulse
            mesh = LiminalMesh(secret_key=github_secret)
            pulse = Pulse(mesh, architect)

    if not mesh.running:
        await mesh.start()

    return f"Connected to Liminal Swarm. Node ID: {mesh.node_id}. Topic: {mesh.topic[:8]}..."

@mcp.tool()
async def share_thought(thought: str) -> str:
    """
    Broadcasts a 'thought' (plan, context, or vector summary) to all other agents.
    """
    if not mesh.running:
        await mesh.start()

    await mesh.share_thought(thought)
    return "Thought streamed to the liminal space."

@mcp.tool()
async def acquire_baton(file_path: str) -> str:
    """
    Acquires an exclusive lock (mutex) on a file.
    Use this before editing critical files to prevent conflicts.
    """
    if not mesh.running:
        await mesh.start()

    success = await mesh.acquire_baton(file_path)
    if success:
        return f"SUCCESS: Baton acquired for {file_path}. You have exclusive write access."
    else:
        owner = mesh.batons.get(file_path, "unknown")
        return f"DENIED: {file_path} is currently locked by agent {owner}."

@mcp.tool()
async def release_baton(file_path: str) -> str:
    """
    Releases the lock on a file.
    Always call this after finishing edits.
    """
    if not mesh.running:
        await mesh.start()

    await mesh.release_baton(file_path)
    # Manually trigger pulse callback since mesh object might have changed
    await pulse.on_baton_release(file_path)
    return f"Baton released for {file_path}."

@mcp.tool()
async def peek_liminal(key: str = None) -> str:
    """
    Reads the shared state of the swarm.
    If key is provided, returns that specific value.
    Otherwise, returns the entire KV store and active thoughts.
    """
    if key:
        val = mesh.get_kv(key)
        return str(val) if val else "Key not found."

    return str({
        "thoughts": mesh.thoughts,
        "batons": mesh.batons,
        "kv": mesh.kv_store
    })

@mcp.tool()
async def consult_architect(context: str) -> str:
    """
    Manually triggers a consultation with the external Architect (Rubber Ducky).
    """
    if not mesh.running:
        await mesh.start()

    await pulse.trigger(context=f"manual:{context}")
    plan = mesh.get_kv("master_plan")
    return f"Architect consulted. Current Master Plan: {plan}"

if __name__ == "__main__":
    mcp.run()
