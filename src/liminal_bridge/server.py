import asyncio
import os
import sys
import argparse
import time
import hashlib

# Get the directory containing this script
current_dir = os.path.dirname(os.path.abspath(__file__))
# Add it to sys.path so we can import 'mesh', 'architect', 'pulse'
sys.path.append(current_dir)

# Handle both relative and absolute imports
try:
    from .mesh import LiminalMesh  # noqa: E402
    from .architect import Architect  # noqa: E402
    from .pulse import Pulse  # noqa: E402
    from .dashboard import DashboardServer  # noqa: E402
except (ImportError, ValueError):
    from mesh import LiminalMesh  # noqa: E402
    from architect import Architect  # noqa: E402
    from pulse import Pulse  # noqa: E402
    from dashboard import DashboardServer  # noqa: E402

from mcp.server.fastmcp import FastMCP  # noqa: E402

# Initialize components
SWARM_KEY = os.getenv("SWARM_KEY", "liminal-default-secret")
# Use environment variables or defaults for persistence
DB_PATH = os.getenv("LIMINAL_DB", "liminal.db")
IDENTITY_PATH = os.getenv("LIMINAL_IDENTITY", "identity.pem")

# Derive stable swarm seed from SWARM_KEY if in seed mode (will be set later if needed)
# For now, default mesh initialization
mesh = None
architect = Architect()
pulse = None  # Will be initialized with mesh
dashboard_server = None  # Will be initialized if requested

# Global args placeholder
args = None

# Create MCP Server
mcp = FastMCP("Keystone-Polyphony")


def ensure_mesh():
    global mesh, pulse
    if mesh is None:
        mesh = LiminalMesh(
            secret_key=SWARM_KEY, db_path=DB_PATH, identity_path=IDENTITY_PATH
        )
        pulse = Pulse(mesh, architect)
        mesh.on_baton_release = pulse.on_baton_release


# --- MCP Tools ---
@mcp.tool()
async def register_to_swarm(github_secret: str = None) -> str:
    """Initializes the connection to the P2P swarm."""
    global mesh, pulse, dashboard_server

    if github_secret and (not mesh or mesh.secret_key != github_secret):
        if mesh and mesh.running:
            await mesh.stop()
        mesh = LiminalMesh(
            secret_key=github_secret, db_path=DB_PATH, identity_path=IDENTITY_PATH
        )
        pulse = Pulse(mesh, architect)
        mesh.on_baton_release = pulse.on_baton_release

    ensure_mesh()

    if not mesh.running:
        await mesh.start()

    # Start dashboard if requested and not running
    if args and args.dashboard_port and not dashboard_server:
        dashboard_server = DashboardServer(mesh, port=args.dashboard_port)
        await dashboard_server.start()

    return f"Connected to Liminal Swarm. Node ID: {mesh.node_id}. Topic: {mesh.topic[:8]}..."


@mcp.tool()
async def share_thought(thought: str) -> str:
    """Broadcasts a 'thought'."""
    ensure_mesh()
    if not mesh.running:
        await mesh.start()
    await mesh.share_thought(thought)
    return "Thought streamed."


@mcp.tool()
async def acquire_baton(file_path: str) -> str:
    """Acquires an exclusive lock on a file."""
    ensure_mesh()
    if not mesh.running:
        await mesh.start()
    success = await mesh.acquire_baton(file_path)
    if success:
        return f"SUCCESS: Baton acquired for {file_path}."
    else:
        owner = mesh.batons.get(file_path, "unknown")
        return f"DENIED: {file_path} is currently locked by {owner}."


@mcp.tool()
async def release_baton(file_path: str) -> str:
    """Releases the lock on a file."""
    ensure_mesh()
    if not mesh.running:
        await mesh.start()
    await mesh.release_baton(file_path)
    # pulse.on_baton_release is now triggered via callback in mesh
    return f"Baton released for {file_path}."


@mcp.tool()
async def peek_liminal(key: str = None) -> str:
    """Reads the shared state."""
    ensure_mesh()
    if key:
        val = mesh.get_kv(key)
        return str(val) if val else "Key not found."
    return str({"thoughts": mesh.thoughts, "batons": mesh.batons, "kv": mesh.kv_store})


@mcp.tool()
async def consult_architect(context: str) -> str:
    """Manually triggers the Architect."""
    ensure_mesh()
    if not mesh.running:
        await mesh.start()
    await pulse.trigger(context=f"manual:{context}")
    plan = mesh.get_kv("master_plan")
    return f"Architect consulted. Plan: {plan}"


# --- Seed Mode ---
async def run_seed_mode(timeout: int = None, dashboard_port: int = None):
    """Runs the mesh in seed mode (no MCP server)."""
    global mesh, pulse

    # Derive stable seed from SWARM_KEY
    swarm_seed = hashlib.sha256(SWARM_KEY.encode()).hexdigest()

    mesh = LiminalMesh(
        secret_key=SWARM_KEY,
        db_path=DB_PATH,
        identity_path=IDENTITY_PATH,
        swarm_seed=swarm_seed,
    )
    pulse = Pulse(mesh, architect)
    mesh.on_baton_release = pulse.on_baton_release

    print(f"Starting Liminal Swarm Seed Node (Key: {SWARM_KEY[:8]}...)...")
    await mesh.start()

    dashboard = None
    if dashboard_port:
        dashboard = DashboardServer(mesh, port=dashboard_port)
        await dashboard.start()

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
        if dashboard:
            await dashboard.stop()
        await mesh.stop()


# --- Verify Mode ---
async def run_verify_mode():
    """Runs a verification test: starts two nodes and checks if they find each other."""
    print("Starting Verification Mode...")

    # Generate random test DB/Identity paths to avoid conflict
    import tempfile
    import shutil

    tmp_dir = tempfile.mkdtemp()
    print(f"Using temp dir: {tmp_dir}")

    try:
        # Node 1: Seed/Anchor
        seed_db = os.path.join(tmp_dir, "seed.db")
        seed_id = os.path.join(tmp_dir, "seed.pem")
        # Use a stable key for the seed to test that part too
        swarm_seed = hashlib.sha256(SWARM_KEY.encode()).hexdigest()

        mesh1 = LiminalMesh(
            secret_key=SWARM_KEY,
            db_path=seed_db,
            identity_path=seed_id,
            swarm_seed=swarm_seed,
        )

        # Node 2: Client
        client_db = os.path.join(tmp_dir, "client.db")
        client_id = os.path.join(tmp_dir, "client.pem")
        mesh2 = LiminalMesh(
            secret_key=SWARM_KEY, db_path=client_db, identity_path=client_id
        )

        print(f"Starting Node 1 (Anchor)... ID: {mesh1.node_id}")
        await mesh1.start()

        print(f"Starting Node 2 (Client)... ID: {mesh2.node_id}")
        await mesh2.start()

        print("Waiting for discovery...")
        # Give it up to 30 seconds
        for i in range(30):
            print(
                f"Check {i+1}/30... Peers: Node1={len(mesh1.peers)}, Node2={len(mesh2.peers)}"
            )
            if len(mesh1.peers) > 0 and len(mesh2.peers) > 0:
                print("SUCCESS: Peers discovered each other!")
                # Optional: Test messaging
                await mesh1.share_thought("Hello from Anchor")
                await asyncio.sleep(1)
                if mesh1.node_id in mesh2.thoughts:
                    print("SUCCESS: Message received!")
                    sys.exit(0)
                else:
                    print("WARNING: Peer connected but message not synced yet.")
                    # Keep waiting a bit
            await asyncio.sleep(1)

        print("FAILURE: Peers did not discover each other within timeout.")
        sys.exit(1)

    finally:
        if "mesh1" in locals() and mesh1.running:
            await mesh1.stop()
        if "mesh2" in locals() and mesh2.running:
            await mesh2.stop()
        shutil.rmtree(tmp_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["mcp", "seed", "verify"],
        default="mcp",
        help="Run mode: 'mcp' server, 'seed' node, or 'verify' test",
    )
    parser.add_argument(
        "--timeout", type=int, default=None, help="Timeout in seconds for seed mode"
    )
    parser.add_argument(
        "--dashboard-port", type=int, default=None, help="Port for the swarm dashboard"
    )

    # FastMCP uses click/typer which might grab args, so we use parse_known_args
    # Use global args so MCP tools can access it
    args, unknown = parser.parse_known_args()

    if args.mode == "seed":
        try:
            asyncio.run(run_seed_mode(args.timeout, args.dashboard_port))
        except KeyboardInterrupt:
            pass
    elif args.mode == "verify":
        try:
            asyncio.run(run_verify_mode())
        except KeyboardInterrupt:
            pass
    else:
        # Clean up argv for FastMCP
        ensure_mesh()
        sys.argv = [sys.argv[0]] + unknown
        mcp.run()
