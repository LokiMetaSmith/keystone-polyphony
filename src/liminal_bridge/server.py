import asyncio
import os
import sys
import argparse
import time
import hashlib
import json

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
SWARM_KEY = os.getenv("SWARM_KEY", "KEYSTONE-POLYPHONY-UPSTREAM")
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

# Global command queue
pending_commands = []

# Create MCP Server
mcp = FastMCP("Keystone-Polyphony")


async def handle_command_request(origin: str, command: dict):
    """Callback for when this node receives a command request."""

    # RBAC Check
    if mesh:
        roles_raw = mesh.get_kv("roles") or []
        origin_role = "user" # default
        for item in roles_raw:
            try:
                role_entry = json.loads(item)
                if role_entry.get("node_id") == origin:
                    origin_role = role_entry.get("role", "user")
                    break
            except Exception:
                continue

        cmd_type = command.get("type")
        if cmd_type in ["execute", "broadcast"] and origin_role != "admin":
            await mesh.log("warn", f"Unauthorized command execution request from {origin}")
            return

    print(f">>> [Command Request] Received from {origin}: {command}")

    # --- Agent Task Handoff & Context Sync Loop for Pollen Inference ---
    if cmd_type == "run_inference":
        prompt = command.get("prompt", "")
        if prompt:
            print(f">>> [Pollen Compute] Executing inference task for {origin}...")
            # We assume architect is configured with pollen_mesh
            # For this simple prototype, we use the `refine_issue` or `consult` method to send the raw prompt
            try:
                # Set status to busy while processing
                await mesh.set_status("busy")

                # Execute via the Architect (which points to Pollen WASM)
                result = await architect._refine_pollen(prompt) if architect.provider == "pollen_mesh" else await architect.refine_issue(prompt)

                # Context Sync Loop: stream the result back to the mesh as a Thought
                await mesh.share_thought(f"Inference Result for {origin}:\n{result}")

            except Exception as e:
                await mesh.share_thought(f"Inference Failed: {e}")
            finally:
                await mesh.set_status("idle")
        return

    # Store standard commands in queue
    pending_commands.append(
        {
            "origin": origin,
            "command": command,
            "timestamp": time.time(),
            "id": hashlib.sha256(f"{origin}:{time.time()}".encode()).hexdigest()[:8],
        }
    )

    # Limit queue size
    if len(pending_commands) > 50:
        pending_commands.pop(0)

    # In MCP mode, we mainly log this so the human/agent can see it in logs/stderr.
    if mesh:
        await mesh.log(
            "info", f"Received command request from {origin}: {command.get('type')}"
        )


def ensure_mesh():
    global mesh, pulse
    if mesh is None:
        mesh = LiminalMesh(
            secret_key=SWARM_KEY, db_path=DB_PATH, identity_path=IDENTITY_PATH
        )
        pulse = Pulse(mesh, architect)
        mesh.on_baton_release = pulse.on_baton_release
        mesh.on_command_request = handle_command_request


def check_warmup(action_type: str) -> str | None:
    """Check if node is still warming up. Returns error message if blocked, None if OK."""
    if mesh is None:
        return None

    if mesh.warmup_complete:
        return None

    status = mesh.get_warmup_status()
    if not status.get("warming_up", False):
        return None

    # Block work actions during warmup
    work_actions = {"claim_task", "complete_task", "acquire_baton", "release_baton"}
    if action_type not in work_actions:
        return None

    remaining = status.get("remaining_silent_timeout", 0)
    elapsed = status.get("elapsed_seconds", 0)

    if status.get("has_conversation"):
        return f"Warming up... Conversation active. Elapsed: {elapsed}s. (Work blocked until conversation ends or 120s timeout)"
    else:
        return f"Warming up... {remaining}s remaining (max 120s silent timeout). Use ensemble_chat to start a conversation."


# --- MCP Tools ---
@mcp.tool()
async def set_status(status: str) -> str:
    """Sets the node status (e.g., 'idle', 'busy') and broadcasts it."""
    ensure_mesh()
    if not mesh.running:
        await mesh.start()
    await mesh.set_status(status)
    return f"Status set to: {status}"


@mcp.tool()
async def broadcast_command(
    command: str,
    target: str = None,
    capabilities: list[str] = None,
    status_filter: str = None,
) -> str:
    """Sends a command execution request to the swarm. command should be a JSON string or description."""
    ensure_mesh()
    if not mesh.running:
        await mesh.start()

    cmd_obj = {"type": "execute", "payload": command}
    await mesh.broadcast_command(
        cmd_obj, target=target, capabilities=capabilities, status_filter=status_filter
    )
    return f"Command broadcasted: {command}"


@mcp.tool()
async def ping(target_node_id: str, message: str = "Ping!") -> str:
    """Sends a direct ping/notification to a specific agent."""
    ensure_mesh()
    if not mesh.running:
        await mesh.start()
    await mesh.ping(target_node_id, message)
    return f"Ping sent to {target_node_id}."


@mcp.tool()
async def list_idle_agents() -> str:
    """Lists all nodes currently in 'idle' status."""
    ensure_mesh()
    if not mesh.running:
        await mesh.start()

    idle = []
    for node_id, thought in mesh.thoughts.items():
        # mesh.thoughts might be enriched dict or raw string
        if isinstance(thought, dict) and thought.get("status") == "idle":
            idle.append(
                {"node_id": node_id, "capabilities": thought.get("capabilities", [])}
            )
        elif isinstance(thought, str):
            try:
                # Try parsing as JSON first
                data = json.loads(thought)
                if data.get("status") == "idle":
                    idle.append(
                        {
                            "node_id": node_id,
                            "capabilities": data.get("capabilities", []),
                        }
                    )
            except BaseException:
                if "status: idle" in thought.lower():
                    idle.append({"node_id": node_id})

    return json.dumps(idle, indent=2)


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

    err = check_warmup("acquire_baton")
    if err:
        return err

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

    err = check_warmup("release_baton")
    if err:
        return err

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


@mcp.tool()
async def ensemble_chat(topic: str, message: str) -> str:
    """Posts a message to a topic-based collaborative discussion thread."""
    ensure_mesh()
    if not mesh.running:
        await mesh.start()

    payload = {
        "sender": mesh.node_id,
        "timestamp": time.time(),
        "content": message,
    }
    # Elements in ORSet must be hashable. JSON string works well.
    await mesh.update_set(f"chat:{topic}", json.dumps(payload))
    return f"Message posted to topic '{topic}'."


@mcp.tool()
async def get_ensemble_chat(topic: str) -> str:
    """Retrieves the history of a collaborative discussion thread, sorted by time."""
    ensure_mesh()
    # We don't strictly need to start the mesh to read local state,
    # but starting ensures we are connected to receive updates.
    if not mesh.running:
        await mesh.start()

    messages_raw = mesh.get_kv(f"chat:{topic}") or []
    messages = []
    for m_json in messages_raw:
        try:
            messages.append(json.loads(m_json))
        except (json.JSONDecodeError, TypeError):
            continue

    # Sort by timestamp
    messages.sort(key=lambda x: x.get("timestamp", 0))
    return json.dumps(messages, indent=2)


@mcp.tool()
async def list_ensemble_chats() -> str:
    """Lists all active collaborative discussion topics (channels)."""
    ensure_mesh()
    if not mesh.running:
        await mesh.start()

    topics = []
    for key in mesh.kv_store.keys():
        if key.startswith("chat:"):
            topics.append(key[5:])
    return json.dumps(topics)


@mcp.tool()
async def mark_chat_read(topic: str) -> str:
    """Marks a collaborative discussion topic as read (local to this node)."""
    ensure_mesh()
    # Store local read timestamp in a special local-only KV or just a file
    # For simplicity, use the mesh metadata or a separate sqlite table
    last_msg = 0
    messages_raw = mesh.get_kv(f"chat:{topic}") or []
    for m_json in messages_raw:
        try:
            ts = json.loads(m_json).get("timestamp", 0)
            last_msg = max(last_msg, ts)
        except:
            continue

    # Save to local metadata
    cursor = mesh.conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
        (f"read_ts:{topic}", str(last_msg)),
    )
    mesh.conn.commit()
    return f"Topic '{topic}' marked as read at {last_msg}."


@mcp.tool()
async def get_unread_chats() -> str:
    """Returns a list of topics with messages that haven't been read locally."""
    ensure_mesh()
    unread = []
    for key in mesh.kv_store.keys():
        if key.startswith("chat:"):
            topic = key[5:]
            # Get last read TS
            cursor = mesh.conn.cursor()
            cursor.execute(
                "SELECT value FROM metadata WHERE key = ?", (f"read_ts:{topic}",)
            )
            row = cursor.fetchone()
            read_ts = float(row[0]) if row else 0

            # Check for newer messages
            has_new = False
            messages_raw = mesh.get_kv(key) or []
            for m_json in messages_raw:
                try:
                    if json.loads(m_json).get("timestamp", 0) > read_ts:
                        has_new = True
                        break
                except:
                    continue

            if has_new:
                unread.append(topic)

    return json.dumps(unread)


@mcp.tool()
async def list_peers() -> str:
    """Lists connected peers in the mesh."""
    ensure_mesh()
    if not mesh.running:
        await mesh.start()
    return json.dumps({"peers": list(mesh.peers), "count": len(mesh.peers)})


@mcp.tool()
async def get_health_status() -> str:
    """Returns the operational health of the mesh node."""
    ensure_mesh()
    if not mesh.running:
        await mesh.start()
    return json.dumps(mesh.get_health_status())


@mcp.tool()
async def get_backlog() -> str:
    """Returns all tasks from the swarm backlog."""
    ensure_mesh()
    if not mesh.running:
        await mesh.start()
    backlog = mesh.get_kv("swarm_backlog") or []
    tasks = []
    for item in backlog:
        try:
            tasks.append(json.loads(item))
        except BaseException:
            continue
    return json.dumps(tasks, indent=2)


@mcp.tool()
async def add_task(title: str, description: str = "", priority: str = "medium") -> str:
    """Adds a new task to the swarm backlog."""
    ensure_mesh()
    if not mesh.running:
        await mesh.start()
    import uuid

    task = {
        "id": str(uuid.uuid4()),
        "title": title,
        "description": description,
        "owner": None,
        "status": "todo",
        "priority": priority,
    }
    await mesh.update_set("swarm_backlog", json.dumps(task))
    return f"Task added: {title} (ID: {task['id']})"


@mcp.tool()
async def claim_task(task_id: str) -> str:
    """Claims a task by ID, acquiring a baton for it."""
    ensure_mesh()
    if not mesh.running:
        await mesh.start()

    err = check_warmup("claim_task")
    if err:
        return err

    # Check dependencies before claiming
    backlog = mesh.get_kv("swarm_backlog") or []
    tasks = []
    target_task = None
    for item in backlog:
        try:
            t = json.loads(item)
            tasks.append(t)
            if t.get("id") == task_id:
                target_task = t
        except BaseException:
            continue

    if target_task:
        task_statuses = {t.get("id"): t.get("status") for t in tasks if t.get("id")}
        blocked_by = target_task.get("blocked_by", [])
        for dep_id in blocked_by:
            if task_statuses.get(dep_id) != "done":
                return f"Failed to claim task {task_id} - unmet dependency: {dep_id}"

    success = await mesh.acquire_baton(f"task:{task_id}")
    if success:
        backlog = mesh.get_kv("swarm_backlog") or []
        for item in backlog:
            try:
                t = json.loads(item)
                if t.get("id") == task_id:
                    t["owner"] = mesh.node_id
                    t["status"] = "in_progress"
                    await mesh.update_set("swarm_backlog", json.dumps(t))
                    break
            except BaseException:
                continue
        return f"Task {task_id} claimed."
    else:
        return f"Failed to claim task {task_id} - baton denied."


@mcp.tool()
async def complete_task(task_id: str) -> str:
    """Marks a task as completed and releases its baton."""
    ensure_mesh()
    if not mesh.running:
        await mesh.start()

    err = check_warmup("complete_task")
    if err:
        return err

    await mesh.release_baton(f"task:{task_id}")
    backlog = mesh.get_kv("swarm_backlog") or []
    for item in backlog:
        try:
            t = json.loads(item)
            if t.get("id") == task_id:
                t["status"] = "done"
                t["owner"] = mesh.node_id
                await mesh.update_set("swarm_backlog", json.dumps(t))
                asyncio.create_task(mesh.log_audit_event("task_completed", {"task_id": task_id}))
                break
        except BaseException:
            continue
    return f"Task {task_id} completed."


@mcp.tool()
async def get_my_node_id() -> str:
    """Returns this node's unique identifier."""
    ensure_mesh()
    if not mesh.running:
        await mesh.start()
    return mesh.node_id


@mcp.tool()
async def get_warmup_status() -> str:
    """Returns the current warmup status of the node."""
    ensure_mesh()
    if not mesh.running:
        await mesh.start()
    status = mesh.get_warmup_status()
    return json.dumps(status, indent=2)


@mcp.tool()
async def get_pending_commands(clear: bool = False) -> str:
    """Retrieves all pending command execution requests sent to this node."""
    global pending_commands
    result = list(pending_commands)
    if clear:
        pending_commands = []
    return json.dumps(result, indent=2)


@mcp.tool()
async def broadcast_message(message: str, urgency: str = "low") -> str:
    """Broadcasts a raw message to all peers."""
    ensure_mesh()
    if not mesh.running:
        await mesh.start()
    await mesh.broadcast({"type": "raw", "content": message}, urgency=urgency)
    return f"Broadcast sent: {message}"


@mcp.tool()
async def notify_agent(target_node_id: str, message: str = "ping") -> str:
    """Sends a high-urgency notification to a specific agent."""
    ensure_mesh()
    if not mesh.running:
        await mesh.start()

    cmd_obj = {"type": "ping", "payload": message}
    await mesh.broadcast_command(cmd_obj, target=target_node_id)
    return f"Ping sent to {target_node_id}."


@mcp.tool()
async def restart_sidecar() -> str:
    """Restarts the Node.js sidecar if it has crashed."""
    ensure_mesh()
    if not mesh.running:
        await mesh.start()
    await mesh.restart_sidecar()
    return "Sidecar restarted."


# --- Seed Mode ---
async def run_seed_mode(timeout: int = None, dashboard_port: int = None):
    """Runs the mesh in seed mode (no MCP server)."""
    global mesh, pulse

    # Determine swarm_seed for identity
    # Priority: 1) explicit --seed arg, 2) --node-name arg (derived), 3) None (random for AI)
    if args and args.seed:
        swarm_seed = args.seed
    elif args and args.node_name:
        swarm_seed = hashlib.sha256(
            f"{SWARM_KEY}:{args.node_name}".encode()
        ).hexdigest()
    else:
        swarm_seed = None  # Random identity for AI nodes

    mesh = LiminalMesh(
        secret_key=SWARM_KEY,
        db_path=DB_PATH,
        identity_path=IDENTITY_PATH,
        swarm_seed=swarm_seed,
    )
    pulse = Pulse(mesh, architect)
    mesh.on_baton_release = pulse.on_baton_release

    if swarm_seed:
        print(
            f"Starting Liminal Swarm Seed Node (Key: {SWARM_KEY[:8]}..., Node Seed: {swarm_seed[:8]}...)"
        )
    else:
        print(
            f"Starting Liminal Swarm Seed Node (Key: {SWARM_KEY[:8]}..., Random Identity)"
        )
    await mesh.start()

    dashboard = None
    if dashboard_port:
        dashboard = DashboardServer(mesh, port=dashboard_port)
        await dashboard.start()

    start_time = time.time()
    last_thought_content = {}

    try:
        while True:
            await asyncio.sleep(1)

            # Check timeout
            if timeout and (time.time() - start_time > timeout):
                print(f"Seed node timeout reached ({timeout}s).")
                break

            # Print flowing thoughts to console
            for node_id, thought in mesh.thoughts.items():
                if isinstance(thought, dict):
                    content = thought.get("content")
                    if content and content != last_thought_content.get(node_id):
                        status = thought.get("status", "unknown")
                        content_str = str(content)
                        short_content = content_str.replace("\n", " ")
                        if len(short_content) > 120:
                            short_content = short_content[:120] + "..."
                        print(
                            f"~~~ [Polyphony] Node {node_id[:8]} ({status}): {short_content}"
                        )
                        last_thought_content[node_id] = content

            # Periodically pulse (every 60s check, but trigger respects cooldown)
            if int(time.time()) % 60 == 0:
                await pulse.trigger(context="seed_heartbeat")
                await pulse.check_baton_health()

            # Autonomous Swarm Behaviors (every 30s)
            if int(time.time()) % 30 == 0:
                # In a real deployment, these would be read from node config
                await mesh.advertise_capabilities(["worker", "compute"])
                task = await mesh.autonomously_pick_task()
                if task:
                    print(f">>> [Autonomy] Node picked task: {task['id']}")

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
                f"Check {i + 1}/30... Peers: Node1={len(mesh1.peers)}, Node2={len(mesh2.peers)}"
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


# --- Daemon Mode ---
async def run_daemon_mode():
    """Runs the mesh as a headless background worker waiting for commands."""
    global mesh, pulse

    # Determine swarm_seed for identity if provided
    if args and args.seed:
        swarm_seed = args.seed
    elif args and args.node_name:
        swarm_seed = hashlib.sha256(
            f"{SWARM_KEY}:{args.node_name}".encode()
        ).hexdigest()
    else:
        swarm_seed = None  # Random identity

    mesh = LiminalMesh(
        secret_key=SWARM_KEY,
        db_path=DB_PATH,
        identity_path=IDENTITY_PATH,
        swarm_seed=swarm_seed,
    )
    pulse = Pulse(mesh, architect)
    mesh.on_baton_release = pulse.on_baton_release
    mesh.on_command_request = handle_command_request

    print(f"Starting Liminal Swarm Daemon Node (Key: {SWARM_KEY[:8]}...)")
    await mesh.start()

    # Worker Node Pattern: register, go idle, and listen
    # We advertise some default developer capabilities
    mesh.capabilities = ["coder", "tester", "researcher"]
    await mesh.set_status("idle")

    try:
        while True:
            await asyncio.sleep(5)
            # In a full agent setup, the local agent process would poll
            # get_pending_commands() via MCP. Here we just keep the mesh
            # alive so the MCP server or agent process can query it.

            # Periodically ensure we broadcast our status if idle too long
            pass
    except asyncio.CancelledError:
        pass
    finally:
        print("Stopping daemon node...")
        await mesh.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["mcp", "seed", "verify", "daemon"],
        default="mcp",
        help="Run mode: 'mcp' server, 'seed' node, 'verify' test, or 'daemon' worker",
    )
    parser.add_argument(
        "--timeout", type=int, default=None, help="Timeout in seconds for seed mode"
    )
    parser.add_argument(
        "--dashboard-port", type=int, default=None, help="Port for the swarm dashboard"
    )
    parser.add_argument(
        "--node-name",
        type=str,
        default=None,
        help="Node name for stable identity (default: random for AI nodes)",
    )
    parser.add_argument(
        "--seed",
        type=str,
        default=None,
        help="Explicit seed for stable identity (overrides --node-name)",
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
    elif args.mode == "daemon":
        try:
            asyncio.run(run_daemon_mode())
        except KeyboardInterrupt:
            pass
    else:
        # Clean up argv for FastMCP
        ensure_mesh()
        sys.argv = [sys.argv[0]] + unknown
        mcp.run()
