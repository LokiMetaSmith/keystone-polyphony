import time
import asyncio
from typing import Any, Dict, Optional, Callable, Awaitable

try:
    from .architect import Architect
except ImportError:
    from architect import Architect

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

        # Gather state
        swarm_state = {
            "thoughts": self.mesh.thoughts,
            "batons": self.mesh.batons,
            "kv": self.mesh.kv_store,
            "context": context
        }

        # Consult
        new_plan = await self.architect.consult(swarm_state)

        # Broadcast the new plan
        await self.mesh.update_kv("master_plan", new_plan)
        self.last_consultation = now
        print(f"PULSE: Plan updated.")

    async def on_baton_release(self, resource: str):
        """
        Callback when a baton is released.
        If it was a critical resource (e.g. core file), trigger a pulse.
        """
        # Heuristic: If 'main' or 'core' is in the resource name, it's critical
        if "main" in resource or "core" in resource or "api" in resource:
            await self.trigger(context=f"baton_released:{resource}")
