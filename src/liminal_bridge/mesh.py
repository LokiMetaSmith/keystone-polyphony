import asyncio
import json
import hashlib
import time
import os
import sqlite3
import base64
from typing import Dict, Optional, Any, Set, Callable, Awaitable
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

try:
    from .observability import LogAggregator
except ImportError:
    from observability import LogAggregator

try:
    from .crdt import CRDT, LWWRegister, PNCounter, GSet, ORSet
except ImportError:
    from crdt import CRDT, LWWRegister, PNCounter, GSet, ORSet


class LiminalMesh:
    def __init__(
        self,
        secret_key: str,
        db_path: str = "liminal.db",
        identity_path: str = "identity.pem",
        bootstrap: Optional[str] = None,
        swarm_seed: Optional[str] = None,
        snapshot_path: str = ".liminal/snapshot.json",
        snapshot_interval: int = 300,
    ):
        self.secret_key = secret_key
        # Generate topic hash for the swarm
        self.topic = hashlib.sha256(secret_key.encode()).hexdigest()
        self.db_path = db_path
        self.identity_path = identity_path
        self.bootstrap = bootstrap
        self.swarm_seed = swarm_seed
        self.snapshot_path = snapshot_path
        self.snapshot_interval = snapshot_interval
        self._snapshot_task: Optional[asyncio.Task] = None

        # Identity Management
        self.private_key = self._load_or_create_identity()
        self.public_key = self.private_key.public_key()

        # Public Key as Hex String for transmission
        pub_bytes = self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        )
        self.public_key_hex = pub_bytes.hex()

        # Stable Node ID derived from Public Key
        self.node_id = hashlib.sha256(pub_bytes).hexdigest()[:16]

        # Encryption Setup
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"liminal-mesh-encryption",
        )
        enc_key = base64.urlsafe_b64encode(hkdf.derive(self.secret_key.encode()))
        self.fernet = Fernet(enc_key)

        self.peers: Set[str] = set()
        self.thoughts: Dict[str, Any] = {}
        self.batons: Dict[str, str] = {}  # resource -> owner_id

        # KV Store now holds CRDT objects
        self.kv_store: Dict[str, CRDT] = {}
        self.vector_clock: Dict[str, int] = {self.node_id: 0}

        # Network Graph
        self.peer_map: Dict[str, str] = {}  # transport_id -> node_id
        self.network_map: Dict[str, list[str]] = {}  # node_id -> [connected_node_ids]

        # Persistence
        self._init_db()
        self._load_state()

        self.process: Optional[asyncio.subprocess.Process] = None
        self.running = False

        # Pending lock requests
        self._lock_requests: Dict[str, asyncio.Future] = {}

        # Callbacks for Pulse
        self.on_baton_release: Optional[Callable[[str, str], Awaitable[None]]] = None

        # Observability
        self.log_aggregator = LogAggregator()

    async def _periodic_snapshot(self):
        """Periodically saves a snapshot of the mesh state."""
        loop = asyncio.get_running_loop()
        while self.running:
            try:
                await asyncio.sleep(self.snapshot_interval)
                await loop.run_in_executor(None, self._save_snapshot)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error saving snapshot: {e}")

            # Also periodically broadcast network state
            await self.broadcast_network_state()

    def _save_snapshot(self):
        """Saves the current state to a JSON file."""
        # Convert CRDTs to dicts for snapshot
        kv_snapshot = {k: v.to_dict() for k, v in self.kv_store.items()}

        data = {
            "timestamp": time.time(),
            "node_id": self.node_id,
            "kv_store": kv_snapshot,
            "thoughts": self.thoughts,
            "batons": self.batons,
            "vector_clock": self.vector_clock,
        }

        # Ensure directory exists
        dirname = os.path.dirname(self.snapshot_path)
        if dirname and not os.path.exists(dirname):
            os.makedirs(dirname, exist_ok=True)

        # Write to a temp file then rename for atomicity
        temp_path = self.snapshot_path + ".tmp"
        with open(temp_path, "w") as f:
            json.dump(data, f, indent=2)

        os.replace(temp_path, self.snapshot_path)

    def _load_or_create_identity(self) -> ed25519.Ed25519PrivateKey:
        """Loads the identity key pair or creates a new one."""
        if os.path.exists(self.identity_path):
            try:
                with open(self.identity_path, "rb") as f:
                    return serialization.load_pem_private_key(f.read(), password=None)
            except Exception as e:
                print(f"Error loading identity: {e}. Generating new one.")

        # Generate new key
        private_key = ed25519.Ed25519PrivateKey.generate()

        # Save it
        with open(self.identity_path, "wb") as f:
            f.write(
                private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )

        return private_key

    def _init_db(self):
        """Initializes the SQLite database."""
        self.conn = sqlite3.connect(self.db_path)
        cursor = self.conn.cursor()

        # Key-Value Store Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS kv_store (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # Thoughts Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS thoughts (
                node_id TEXT PRIMARY KEY,
                content TEXT
            )
        """)

        # Metadata Table (for Vector Clock)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        self.conn.commit()

    def _deserialize_crdt(self, data: Any) -> CRDT:
        """Helper to deserialize JSON data into a CRDT object."""
        if isinstance(data, dict):
            crdt_type = data.get("type")
            if crdt_type == "lww-register":
                return LWWRegister.from_dict(data)
            elif crdt_type == "pn-counter":
                return PNCounter.from_dict(data)
            elif crdt_type == "g-set":
                return GSet.from_dict(data)
            elif crdt_type == "or-set":
                return ORSet.from_dict(data)
            elif "vc" in data and "value" in data:
                # Legacy wrapped format -> LWWRegister
                return LWWRegister(
                    value=data["value"],
                    timestamp=data.get("timestamp", 0),
                    origin=data.get("origin", "unknown"),
                    vc=data["vc"],
                )

        # Raw value -> LWWRegister with empty VC (should ideally not happen in new system)
        return LWWRegister(value=data, timestamp=0, origin="unknown", vc={})

    def _load_state(self):
        """Loads state from the database."""
        cursor = self.conn.cursor()

        # Load KV
        cursor.execute("SELECT key, value FROM kv_store")
        for key, value_json in cursor.fetchall():
            try:
                data = json.loads(value_json)
                self.kv_store[key] = self._deserialize_crdt(data)
            except json.JSONDecodeError:
                pass

        # Load Thoughts
        cursor.execute("SELECT node_id, content FROM thoughts")
        for node_id, content in cursor.fetchall():
            self.thoughts[node_id] = content

        # Load Vector Clock
        try:
            cursor.execute("SELECT value FROM metadata WHERE key = 'vector_clock'")
            row = cursor.fetchone()
            if row:
                self.vector_clock = json.loads(row[0])
            else:
                self.vector_clock = {self.node_id: 0}
        except Exception:
            self.vector_clock = {self.node_id: 0}

    def _save_kv(self, key: str, value: CRDT):
        """Persists a KV update."""
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO kv_store (key, value) VALUES (?, ?)",
            (key, json.dumps(value.to_dict())),
        )
        self.conn.commit()

    def _save_clock(self):
        """Persists the vector clock."""
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ("vector_clock", json.dumps(self.vector_clock)),
        )
        self.conn.commit()

    def _save_thought(self, node_id: str, content: str):
        """Persists a thought."""
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO thoughts (node_id, content) VALUES (?, ?)",
            (node_id, content),
        )
        self.conn.commit()

    async def join_swarms(self, keys: list[str]):
        """Joins additional swarm topics."""
        for key in keys:
            topic_hex = hashlib.sha256(key.encode()).hexdigest()
            await self._send_to_sidecar("join", {"topic": topic_hex})

    async def leave_swarms(self, keys: list[str]):
        """Leaves swarm topics."""
        for key in keys:
            topic_hex = hashlib.sha256(key.encode()).hexdigest()
            await self._send_to_sidecar("leave", {"topic": topic_hex})

    async def rotate_key(self, new_key: str, grace_period: float = 0):
        """Rotates the swarm key."""
        old_key = self.secret_key

        # Join new swarm immediately
        await self.join_swarms([new_key])

        # Update current key
        self.secret_key = new_key
        self.topic = hashlib.sha256(new_key.encode()).hexdigest()

        # Schedule leave of old swarm
        if grace_period > 0:
            asyncio.create_task(self._delayed_leave(old_key, grace_period))
        else:
            await self.leave_swarms([old_key])

    async def _delayed_leave(self, key: str, delay: float):
        await asyncio.sleep(delay)
        await self.leave_swarms([key])

    async def _ensure_sidecar_deps(self, sidecar_dir: str):
        """Ensures Node.js dependencies are installed asynchronously."""
        node_modules = os.path.join(sidecar_dir, "node_modules")
        if not os.path.exists(node_modules):
            print(f"Installing sidecar dependencies in {sidecar_dir}...")
            try:
                # check if npm is installed
                proc = await asyncio.create_subprocess_exec(
                    "npm",
                    "--version",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await proc.wait()
                if proc.returncode != 0:
                    print("Warning: npm not found. Sidecar may fail to start.")
                    return

                # install dependencies
                install_proc = await asyncio.create_subprocess_exec(
                    "npm",
                    "install",
                    cwd=sidecar_dir,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await install_proc.communicate()

                if install_proc.returncode == 0:
                    print("Dependencies installed successfully.")
                else:
                    print(
                        f"Warning: Failed to install dependencies. Sidecar may fail to start.\nError: {stderr.decode()}"
                    )
            except Exception as e:
                print(f"Error during dependency check: {e}")

    async def start(self):
        """Starts the Node.js sidecar and begins listening."""
        self.running = True

        # Locate the sidecar script
        current_dir = os.path.dirname(os.path.abspath(__file__))
        sidecar_dir = os.path.join(current_dir, "sidecar")
        sidecar_path = os.path.join(sidecar_dir, "bridge.js")

        # Ensure dependencies
        await self._ensure_sidecar_deps(sidecar_dir)

        # Start Node.js process
        args = ["node", sidecar_path, self.topic]
        if self.bootstrap:
            args.extend(["--bootstrap", self.bootstrap])
        if self.swarm_seed:
            args.extend(["--seed", self.swarm_seed])

        self.process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Start reading stdout in background
        asyncio.create_task(self._read_stdout())
        asyncio.create_task(self._read_stderr())

        # Start snapshot task
        self._snapshot_task = asyncio.create_task(self._periodic_snapshot())

        # Broadcast initial state (so dashboard sees us)
        asyncio.create_task(self.broadcast_network_state())

        print(
            f"LiminalMesh started. Node ID: {self.node_id}. Topic: {self.topic[:8]}..."
        )

    async def stop(self):
        """Stops the sidecar."""
        self.running = False

        if self._snapshot_task:
            self._snapshot_task.cancel()
            try:
                await self._snapshot_task
            except asyncio.CancelledError:
                pass

        if self.process:
            try:
                self.process.terminate()
                await self.process.wait()
            except ProcessLookupError:
                pass  # Process already dead

        if self.conn:
            self.conn.close()

    async def _read_stdout(self):
        """Reads JSON messages from the sidecar."""
        if not self.process or not self.process.stdout:
            return

        while self.running:
            line = await self.process.stdout.readline()
            if not line:
                break

            try:
                msg = json.loads(line.decode().strip())
                await self._handle_message(msg)
            except json.JSONDecodeError:
                print(f"DEBUG: Malformed line from sidecar: {line}")
            except Exception as e:
                print(f"Error handling message: {e}")

    async def _read_stderr(self):
        """Reads stderr from the sidecar (logs)."""
        if not self.process or not self.process.stderr:
            return

        while self.running:
            line = await self.process.stderr.readline()
            if not line:
                break
            print(f"SIDECAR LOG: {line.decode().strip()}")

    async def _send_to_sidecar(self, msg_type: str, payload: Any):
        """Sends a JSON command to the sidecar."""
        if not self.process or not self.process.stdin:
            return

        msg = json.dumps({"type": msg_type, "payload": payload}) + "\n"
        self.process.stdin.write(msg.encode())
        await self.process.stdin.drain()

    def _encrypt(self, payload: Any) -> str:
        """Encrypts a payload dictionary to a base64 string."""
        data = json.dumps(payload).encode()
        return self.fernet.encrypt(data).decode()

    def _decrypt(self, encrypted_b64: str) -> Any:
        """Decrypts a base64 string to a payload dictionary."""
        data = self.fernet.decrypt(encrypted_b64.encode())
        return json.loads(data.decode())

    async def broadcast(self, payload: Any):
        """Broadcasts a payload to all peers."""
        # Attach origin info
        payload["origin"] = self.node_id
        payload["timestamp"] = time.time()
        # Include public key for identification (could be optimized to only send once, but simplified here)
        payload["sender_pubkey"] = self.public_key_hex

        # Attach vector clock if not already present (some calls might add it explicitly)
        if "vc" not in payload:
            payload["vc"] = self.vector_clock

        # Encrypt the payload before sending
        encrypted_data = self._encrypt(payload)
        await self._send_to_sidecar("broadcast", {"e": encrypted_data})

    def _increment_clock(self):
        """Increments the local logical clock."""
        self.vector_clock[self.node_id] = self.vector_clock.get(self.node_id, 0) + 1
        self._save_clock()

    def _merge_clock(self, remote_clock: Dict[str, int]):
        """Merges a remote vector clock into the local one."""
        for node, count in remote_clock.items():
            self.vector_clock[node] = max(self.vector_clock.get(node, 0), count)
        self._save_clock()

    async def _handle_message(self, msg: Dict[str, Any]):
        """Dispatches incoming messages."""
        msg_type = msg.get("type")

        if msg_type == "peer_connected":
            print(f"DEBUG: Node {self.node_id} connected to peer {msg.get('peer_id')}")
            self.peers.add(msg.get("peer_id"))
            # Re-broadcast my state to new peer
            if self.node_id in self.thoughts:
                await self.share_thought(self.thoughts[self.node_id])
            await self.broadcast_network_state()

        elif msg_type == "peer_disconnected":
            pid = msg.get("peer_id")
            if pid in self.peers:
                self.peers.remove(pid)
            await self.broadcast_network_state()

        elif msg_type == "message":
            payload = msg.get("payload", {})

            # Decrypt if encrypted
            if "e" in payload:
                try:
                    payload = self._decrypt(payload["e"])
                except Exception as e:
                    print(f"Error decrypting message from {msg.get('peer_id')}: {e}")
                    return

            # Update peer map
            origin = payload.get("origin")
            peer_id = msg.get("peer_id")
            if origin and peer_id:
                self.peer_map[peer_id] = origin

            await self._handle_payload(payload)

    async def _handle_payload(self, payload: Dict[str, Any]):
        """Handles application-level logic."""
        p_type = payload.get("type")
        origin = payload.get("origin")
        remote_vc = payload.get("vc", {})

        # Merge clocks on receive
        if remote_vc:
            self._merge_clock(remote_vc)

        if p_type == "thought":
            content = payload.get("content")
            self.thoughts[origin] = content
            self._save_thought(origin, content)

        elif p_type == "kv_update":
            key = payload.get("key")
            crdt_data = payload.get("crdt")

            if crdt_data:
                # New CRDT-based update
                remote_crdt = self._deserialize_crdt(crdt_data)

                # Check if we have a local CRDT for this key
                current = self.kv_store.get(key)

                if current and isinstance(current, type(remote_crdt)):
                    # Merge
                    current.merge(remote_crdt)
                    self._save_kv(key, current)
                else:
                    # Overwrite or New
                    # For LWWRegister, we might want to check causality vs current if types mismatch?
                    # For simplicity, if types mismatch, we overwrite with the incoming one
                    # (assuming the network converges to the new type eventually).
                    self.kv_store[key] = remote_crdt
                    self._save_kv(key, remote_crdt)

            else:
                # Legacy update (LWWRegister implicit)
                value = payload.get("value")
                remote_ts = payload.get("timestamp", 0)

                remote_lww = LWWRegister(value, remote_ts, origin, remote_vc)

                current = self.kv_store.get(key)
                if current and isinstance(current, LWWRegister):
                    current.merge(remote_lww)
                    self._save_kv(key, current)
                elif current is None:
                    self.kv_store[key] = remote_lww
                    self._save_kv(key, remote_lww)
                else:
                    # Type mismatch (Current is Counter/Set, incoming is LWW).
                    # We keep current? Or overwrite?
                    # Assuming migration to CRDTs, LWW is the 'default'.
                    # If we have a Counter, we probably don't want to overwrite with a Register.
                    # But for now, let's assume strict typing per key.
                    pass

        elif p_type == "baton_request":
            resource = payload.get("resource")
            # If I hold the lock, deny
            if self.batons.get(resource) == self.node_id:
                await self.broadcast(
                    {
                        "type": "baton_deny",
                        "resource": resource,
                        "target": origin,
                        "reason": "I hold the lock",
                    }
                )

        elif p_type == "baton_claim":
            resource = payload.get("resource")
            self.batons[resource] = origin

        elif p_type == "baton_release":
            resource = payload.get("resource")
            if self.batons.get(resource) == origin:
                del self.batons[resource]

        elif p_type == "baton_deny":
            resource = payload.get("resource")
            target = payload.get("target")
            if target == self.node_id:
                if resource in self._lock_requests:
                    self._lock_requests[resource].set_result(False)

        elif p_type == "log":
            # Add remote log to aggregator
            self.log_aggregator.add_log(payload)

        elif p_type == "peer_update":
            # Update network map
            node = payload.get("node")
            peers = payload.get("peers", [])
            if node:
                self.network_map[node] = peers

    async def broadcast_network_state(self):
        """Broadcasts the current list of connected peers (Node IDs)."""
        # Resolve peers to node IDs
        connected_nodes = []
        for pid in self.peers:
            if pid in self.peer_map:
                connected_nodes.append(self.peer_map[pid])

        # Update local map
        self.network_map[self.node_id] = connected_nodes

        # Broadcast
        await self.broadcast(
            {"type": "peer_update", "node": self.node_id, "peers": connected_nodes}
        )

    # --- Public API ---

    async def log(self, level: str, message: str):
        """Broadcasts a log message."""
        entry = {
            "type": "log",
            "level": level,
            "message": message,
            "origin": self.node_id,
            "timestamp": time.time(),
        }
        self.log_aggregator.add_log(entry)
        await self.broadcast(entry)

    async def share_thought(self, content: str):
        self.thoughts[self.node_id] = content
        self._save_thought(self.node_id, content)
        await self.broadcast({"type": "thought", "content": content})

    async def update_kv(self, key: str, value: Any):
        """Updates a Key-Value pair using LWWRegister."""
        self._increment_clock()
        timestamp = time.time()

        current = self.kv_store.get(key)

        if current and not isinstance(current, LWWRegister):
            # If it was another CRDT type, we are overwriting it with a Register
            pass

        new_register = LWWRegister(
            value, timestamp, self.node_id, self.vector_clock.copy()
        )

        # If we had a previous LWWRegister, we might want to merge just to be safe (idempotency),
        # but here we are originating a new value, so we just set it.
        # Actually, if we want to preserve history? LWWRegister doesn't preserve history, just latest.

        self.kv_store[key] = new_register
        self._save_kv(key, new_register)

        # Broadcast
        await self.broadcast(
            {"type": "kv_update", "key": key, "crdt": new_register.to_dict()}
        )

    async def update_counter(self, key: str, delta: int = 1):
        """Updates a PNCounter."""
        self._increment_clock()  # Counters don't strictly use VC for merge, but good to track causality in mesh

        current = self.kv_store.get(key)
        if current is None:
            current = PNCounter()
            self.kv_store[key] = current
        elif not isinstance(current, PNCounter):
            raise ValueError(f"Key {key} is not a PNCounter")

        if delta > 0:
            current.inc(self.node_id, delta)
        elif delta < 0:
            current.dec(self.node_id, -delta)

        self._save_kv(key, current)

        await self.broadcast(
            {"type": "kv_update", "key": key, "crdt": current.to_dict()}
        )

    async def update_set(self, key: str, element: Any, remove: bool = False):
        """Updates an ORSet (or GSet if remove=False and fallback)."""
        self._increment_clock()

        current = self.kv_store.get(key)
        if current is None:
            current = ORSet()
            self.kv_store[key] = current
        elif not isinstance(current, ORSet):
            raise ValueError(f"Key {key} is not an ORSet")

        if remove:
            current.remove(element)
        else:
            current.add(element)

        self._save_kv(key, current)

        await self.broadcast(
            {"type": "kv_update", "key": key, "crdt": current.to_dict()}
        )

    def get_kv(self, key: str):
        val = self.kv_store.get(key)
        if val is None:
            return None
        return val.value()

    def get_all_kv(self) -> Dict[str, Any]:
        """Returns a copy of the KV store with values unwrapped."""
        return {k: v.value() for k, v in self.kv_store.items()}

    async def acquire_baton(self, resource: str, timeout: float = 2.0) -> bool:
        """Tries to acquire a lock on a resource."""
        if resource in self.batons:
            if self.batons[resource] == self.node_id:
                return True
            return False

        future = asyncio.get_running_loop().create_future()
        self._lock_requests[resource] = future

        await self.broadcast({"type": "baton_request", "resource": resource})

        try:
            await asyncio.wait_for(future, timeout=timeout)
            result = future.result()
            del self._lock_requests[resource]
            return result
        except asyncio.TimeoutError:
            del self._lock_requests[resource]
            self.batons[resource] = self.node_id
            await self.broadcast({"type": "baton_claim", "resource": resource})
            return True

    async def release_baton(self, resource: str):
        if self.batons.get(resource) == self.node_id:
            del self.batons[resource]
            await self.broadcast({"type": "baton_release", "resource": resource})
            # Trigger Pulse
            if self.on_baton_release:
                # Pass resource and my identity
                await self.on_baton_release(resource, self.node_id)
