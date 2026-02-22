import asyncio
import json
import hashlib
import time
import sys
import os
from typing import Dict, Optional, Any, Set, Callable, Awaitable

class LiminalMesh:
    def __init__(self, secret_key: str):
        self.secret_key = secret_key
        # Generate topic hash for the swarm
        self.topic = hashlib.sha256(secret_key.encode()).hexdigest()
        self.node_id = hashlib.sha256((secret_key + str(time.time()) + str(os.getpid())).encode()).hexdigest()[:16]

        self.peers: Set[str] = set()
        self.thoughts: Dict[str, Any] = {}
        self.batons: Dict[str, str] = {}  # resource -> owner_id
        self.kv_store: Dict[str, Any] = {}

        self.process: Optional[asyncio.subprocess.Process] = None
        self.running = False

        # Pending lock requests
        self._lock_requests: Dict[str, asyncio.Future] = {}

        # Callbacks for Pulse
        self.on_baton_release: Optional[Callable[[str], Awaitable[None]]] = None

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

        if p_type == "thought":
            self.thoughts[origin] = payload.get("content")

        elif p_type == "kv_update":
            key = payload.get("key")
            value = payload.get("value")
            # Last Write Wins (using timestamp)
            self.kv_store[key] = value

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
        await self.broadcast({
            "type": "thought",
            "content": content
        })

    async def update_kv(self, key: str, value: Any):
        self.kv_store[key] = value
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
                await self.on_baton_release(resource)
