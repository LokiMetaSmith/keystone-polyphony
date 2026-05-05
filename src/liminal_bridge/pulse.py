import json
import time
from typing import Any

try:
    from .architect import Architect
except ImportError:
    from architect import Architect


def _serialize_for_json(obj):
    """Convert objects to JSON-serializable format."""
    if isinstance(obj, set):
        return list(obj)
    elif isinstance(obj, dict):
        return {k: _serialize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_serialize_for_json(item) for item in obj]
    else:
        return obj


class Pulse:
    def __init__(self, mesh: Any, architect: Architect):
        self.mesh = mesh
        self.architect = architect
        self.last_consultation = 0.0
        self.cooldown = 300.0  # 5 minutes between automatic consultations

    async def trigger(self, context: str = "routine_check"):
        """
        Manually triggers a consultation if cooldown has passed.
        """
        now = time.time()
        if now - self.last_consultation < self.cooldown and context != "force":
            return

        print(f"PULSE: Triggering Architect consultation ({context})...")

        # Gather state - serialize to ensure JSON compatibility
        raw_state = {
            "thoughts": self.mesh.thoughts,
            "batons": self.mesh.batons,
            "kv": self.mesh.get_all_kv(),
            "context": context,
        }
        swarm_state = _serialize_for_json(raw_state)

        # Consult
        new_plan_raw = await self.architect.consult(swarm_state)

        try:
            new_plan = json.loads(new_plan_raw)
        except json.JSONDecodeError:
            # Fallback if it's just a string or malformed
            new_plan = {"backlog": new_plan_raw}

        # Broadcast the new plan to KV
        await self.mesh.update_kv("master_plan", new_plan)

        # Execute commands if any
        if isinstance(new_plan, dict) and "commands" in new_plan:
            for cmd_req in new_plan["commands"]:
                target = cmd_req.get("target")
                command = cmd_req.get("command")
                caps = cmd_req.get("capabilities", [])
                if command:
                    print(
                        f"PULSE: Issuing command to {target or 'capable agents'}: {command}"
                    )
                    await self.mesh.broadcast_command(
                        {"type": "architect_execute", "payload": command},
                        target=target,
                        capabilities=caps,
                    )

        self.last_consultation = now
        print("PULSE: Plan updated and commands issued.")

    async def check_baton_health(self):
        """
        Iterates over active batons. If the owner's last thought is older than 5 minutes (300s),
        release the baton by broadcasting baton_release.
        """
        now = time.time()
        for resource, owner in list(self.mesh.batons.items()):
            thought = self.mesh.thoughts.get(owner)
            if not thought:
                continue

            last_activity = thought.get("timestamp", 0)
            if now - last_activity > 300:
                print(
                    f"PULSE: Baton {resource} held by {owner} appears stale. Broadcasting release."
                )
                # We can originate the release from our own node_id, we will update mesh.py to allow it
                await self.mesh.broadcast(
                    {
                        "type": "baton_release",
                        "resource": resource,
                        "force": True,  # Add a force flag for mesh to recognize
                    }
                )

    async def on_baton_release(self, resource: str, agent_id: str):
        """
        Callback when a baton is released.
        If it was a critical resource (e.g. core file), trigger a pulse.
        """
        # Heuristic: If 'main' or 'core' is in the resource name, it's critical
        if "main" in resource or "core" in resource or "api" in resource:
            await self.trigger(context=f"baton_released:{resource} by {agent_id}")
