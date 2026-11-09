"""Optional trusted input boundary, supplied by the task owner on the service host.

Providers return ONLY approved worker inputs. Raw private instructions, memory,
paths and provider source data must never be copied to public durable records.
The service passes this value directly to stdin and does not persist it.
"""

from typing import Protocol


class ApprovedInputProvider(Protocol):
    def worker_input(self, task_id: str, public_requirements: str) -> str:
        """Return the owner's approved input for one worker execution."""
        ...


class PublicRequirements:
    def worker_input(self, task_id: str, public_requirements: str) -> str:
        return public_requirements
