import asyncio
import json
import hashlib
import time
import sys
import os
import sqlite3
from typing import Dict, Optional, Any, Set, Callable, Awaitable
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

class LiminalMesh:
    def __init__(self, secret_key: str, db_path: str = "liminal.db", identity_path: str = "identity.pem"):
        self.secret_key = secret_key
        # Generate topic hash for the swarm
        self.topic = hashlib.sha256(secret_key.encode()).hexdigest()
        self.db_path = db_path
        self.identity_path = identity_path

        # Identity Management
        self.private_key = self._load_or_create_identity()
        self.public_key = self.private_key.public_key()

        # Public Key as Hex String for transmission
        pub_bytes = self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        self.public_key_hex = pub_bytes.hex()

        # Stable Node ID derived from Public Key
        self.node_id = hashlib.sha256(pub_bytes).hexdigest()[:16]

        self.peers: Set[str] = set()
        self.thoughts: Dict[str, Any] = {}
        self.batons: Dict[str, str] = {}  # resource -> owner_id
        self.kv_store: Dict[str, Any] = {}

        # Persistence
        self._init_db()
        self._load_state()

        self.process: Optional[asyncio.subprocess.Process] = None
        self.running = False

        # Pending lock requests
        self._lock_requests: Dict[str, asyncio.Future] = {}

        # Callbacks for Pulse
        self.on_baton_release: Optional[Callable[[str, str], Awaitable[None]]] = None

    def _load_or_create_identity(self) -> ed25519.Ed25519PrivateKey:
        """Loads the identity key pair or creates a new one."""
        if os.path.exists(self.identity_path):
            try:
                with open(self.identity_path, "rb") as f:
                    return serialization.load_pem_private_key(
                        f.read(),
                        password=None
                    )
            except Exception as e:
                print(f"Error loading identity: {e}. Generating new one.")

        # Generate new key
        private_key = ed25519.Ed25519PrivateKey.generate()

        # Save it
        with open(self.identity_path, "wb") as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ))

        return private_key

    def _init_db(self):
        """Initializes the SQLite database."""
        self.conn = sqlite3.connect(self.db_path)
        cursor = self.conn.cursor()

        # Key-Value Store Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS kv_store (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')

        # Thoughts Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS thoughts (
                node_id TEXT PRIMARY KEY,
                content TEXT
            )
        ''')
        self.conn.commit()

    def _load_state(self):
        """Loads state from the database."""
        cursor = self.conn.cursor()

        # Load KV
        cursor.execute("SELECT key, value FROM kv_store")
        for key, value_json in cursor.fetchall():
            try:
                self.kv_store[key] = json.loads(value_json)
            except json.JSONDecodeError:
                pass

        # Load Thoughts
        cursor.execute("SELECT node_id, content FROM thoughts")
        for node_id, content in cursor.fetchall():
            self.thoughts[node_id] = content

    def _save_kv(self, key: str, value: Any):
        """Persists a KV update."""
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO kv_store (key, value) VALUES (?, ?)",
            (key, json.dumps(value))
        )
        self.conn.commit()

    def _save_thought(self, node_id: str, content: str):
        """Persists a thought."""
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO thoughts (node_id, content) VALUES (?, ?)",
            (node_id, content)
        )
        self.conn.commit()

    async def start(self):
        """Starts the Node.js sidecar and begins listening."""
        self.running = True

        # Locate the sidecar script
        current_dir = os.path.dirname(os.path.abspath(__file__))
        sidecar_path = os.path.join(current_dir, "sidecar", "bridge.js")

        # Start Node.js process
        self.process = await asyncio.create_subprocess_exec(
            "node", sidecar_path, self.topic,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # Start reading stdout in background
        asyncio.create_task(self._read_stdout())
        asyncio.create_task(self._read_stderr())

        print(f"LiminalMesh started. Node ID: {self.node_id}. Topic: {self.topic[:8]}...")

    async def stop(self):
        """Stops the sidecar."""
        self.running = False
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
            # print(f"SIDECAR LOG: {line.decode().strip()}")

    async def _send_to_sidecar(self, msg_type: str, payload: Any):
        """Sends a JSON command to the sidecar."""
        if not self.process or not self.process.stdin:
            return

        msg = json.dumps({"type": msg_type, "payload": payload}) + "\n"
        self.process.stdin.write(msg.encode())
        await self.process.stdin.drain()

    async def broadcast(self, payload: Any):
        """Broadcasts a payload to all peers."""
        # Attach origin info
        payload["origin"] = self.node_id
        payload["timestamp"] = time.time()
        # Include public key for identification (could be optimized to only send once, but simplified here)
        payload["sender_pubkey"] = self.public_key_hex

        await self._send_to_sidecar("broadcast", payload)

    async def _handle_message(self, msg: Dict[str, Any]):
        """Dispatches incoming messages."""
        msg_type = msg.get("type")

        if msg_type == "peer_connected":
            self.peers.add(msg.get("peer_id"))
            # Re-broadcast my state to new peer
            if self.node_id in self.thoughts:
                await self.share_thought(self.thoughts[self.node_id])

        elif msg_type == "peer_disconnected":
            pid = msg.get("peer_id")
            if pid in self.peers:
                self.peers.remove(pid)

        elif msg_type == "message":
            payload = msg.get("payload", {})
            await self._handle_payload(payload)

    async def _handle_payload(self, payload: Dict[str, Any]):
        """Handles application-level logic."""
        p_type = payload.get("type")
        origin = payload.get("origin")

        # Future: Validate signature using payload.get("sender_pubkey")

        if p_type == "thought":
            content = payload.get("content")
            self.thoughts[origin] = content
            self._save_thought(origin, content)

        elif p_type == "kv_update":
            key = payload.get("key")
            value = payload.get("value")
            # Last Write Wins (using timestamp)
            self.kv_store[key] = value
            self._save_kv(key, value)

        elif p_type == "baton_request":
            resource = payload.get("resource")
            # If I hold the lock, deny
            if self.batons.get(resource) == self.node_id:
                await self.broadcast({
                    "type": "baton_deny",
                    "resource": resource,
                    "target": origin,
                    "reason": "I hold the lock"
                })

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

    # --- Public API ---

    async def share_thought(self, content: str):
        self.thoughts[self.node_id] = content
        self._save_thought(self.node_id, content)
        await self.broadcast({
            "type": "thought",
            "content": content
        })

    async def update_kv(self, key: str, value: Any):
        self.kv_store[key] = value
        self._save_kv(key, value)
        await self.broadcast({
            "type": "kv_update",
            "key": key,
            "value": value
        })

    def get_kv(self, key: str):
        return self.kv_store.get(key)

    def get_all_kv(self) -> Dict[str, Any]:
        return self.kv_store

    async def acquire_baton(self, resource: str, timeout: float = 2.0) -> bool:
        """Tries to acquire a lock on a resource."""
        if resource in self.batons:
            if self.batons[resource] == self.node_id:
                return True
            return False

        future = asyncio.get_running_loop().create_future()
        self._lock_requests[resource] = future

        await self.broadcast({
            "type": "baton_request",
            "resource": resource
        })

        try:
            await asyncio.wait_for(future, timeout=timeout)
            result = future.result()
            del self._lock_requests[resource]
            return result
        except asyncio.TimeoutError:
            del self._lock_requests[resource]
            self.batons[resource] = self.node_id
            await self.broadcast({
                "type": "baton_claim",
                "resource": resource
            })
            return True

    async def release_baton(self, resource: str):
        if self.batons.get(resource) == self.node_id:
            del self.batons[resource]
            await self.broadcast({
                "type": "baton_release",
                "resource": resource
            })
            # Trigger Pulse
            if self.on_baton_release:
                # Pass resource and my identity
                await self.on_baton_release(resource, self.node_id)
