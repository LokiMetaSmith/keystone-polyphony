"""Self-organizing Conductor agent and advisory nudges.

Strictly non-coding and non-blocking: observes contention and telemetry,
emits deduplicated advisory nudges with cooldowns/expiries, and guides workers to uncontested tasks.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
import time
import hashlib
from .models import TaskObjective, TaskStatus
from .ledger import FencedLedger


@dataclass
class AdvisoryNudge:
    nudge_id: str
    task_id: str
    target_actor_id: Optional[str]
    suggested_action: str
    rationale: str
    suggested_alternative_task_ids: List[str] = field(default_factory=list)
    expires_at: float = field(default_factory=lambda: time.time() + 300.0)
    created_at: float = field(default_factory=time.time)

    def is_expired(self, now: Optional[float] = None) -> bool:
        t = now if now is not None else time.time()
        return t > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nudge_id": self.nudge_id,
            "task_id": self.task_id,
            "target_actor_id": self.target_actor_id,
            "suggested_action": self.suggested_action,
            "rationale": self.rationale,
            "suggested_alternative_task_ids": self.suggested_alternative_task_ids,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
        }


class EnsembleConductor:
    """
    Cognitive Conductor: observes coordinator telemetry and task contention.
    Does NOT write code or edit files. Emits advisory nudges to route workers.
    """

    def __init__(self, ledger: FencedLedger, nudge_cooldown_seconds: float = 60.0):
        self.ledger = ledger
        self.nudge_cooldown = nudge_cooldown_seconds
        self.emitted_nudges: Dict[str, float] = {}  # nudge_fingerprint -> timestamp
        self.active_nudges: List[AdvisoryNudge] = []

    def observe_contention_and_nudge(
        self,
        contested_task_id: str,
        blocked_actor_id: str,
        now: Optional[float] = None,
    ) -> Optional[AdvisoryNudge]:
        """
        Invoked when a worker encounters 409 Conflict on a task.
        Identifies alternative eligible tasks and emits a deduplicated advisory nudge.
        """
        current_time = now if now is not None else time.time()

        # Find uncontested eligible tasks
        all_tasks = self.ledger.list_tasks()
        uncontested = [
            t.task_id
            for t in all_tasks
            if t.task_id != contested_task_id
            and t.status in (TaskStatus.OPEN, TaskStatus.INTEGRATING)
            and t.current_assignment_id is None
        ]

        # Fingerprint for deduplication and cooldown
        fingerprint = hashlib.sha256(
            f"{contested_task_id}:{blocked_actor_id}".encode()
        ).hexdigest()

        last_emitted = self.emitted_nudges.get(fingerprint, 0.0)
        if (current_time - last_emitted) < self.nudge_cooldown:
            # Under cooldown; do not spam nudges
            return None

        nudge_id = f"nudge_{fingerprint[:12]}"
        action = (
            f"Pivot to alternative uncontested tasks: {uncontested[:3]}"
            if uncontested
            else "Wait with exponential backoff or assist in integration review"
        )
        rationale = f"Task {contested_task_id} is currently claimed and contested."

        nudge = AdvisoryNudge(
            nudge_id=nudge_id,
            task_id=contested_task_id,
            target_actor_id=blocked_actor_id,
            suggested_action=action,
            rationale=rationale,
            suggested_alternative_task_ids=uncontested[:5],
            expires_at=current_time + 180.0,
            created_at=current_time,
        )

        self.emitted_nudges[fingerprint] = current_time
        self.active_nudges.append(nudge)
        return nudge

    def get_active_nudges_for_actor(
        self, actor_id: str, now: Optional[float] = None
    ) -> List[AdvisoryNudge]:
        current_time = now if now is not None else time.time()
        # Filter unexpired nudges for this actor or broadcast (target None)
        valid = [
            n
            for n in self.active_nudges
            if not n.is_expired(current_time)
            and (n.target_actor_id is None or n.target_actor_id == actor_id)
        ]
        return valid


class WorkerFlowManager:
    """
    Manages client/worker loop invariants:
    - Never spin or block indefinitely on a contested baton.
    - If 409 Conflict is received, immediately pivot to an uncontested eligible task or review.
    """

    def __init__(self, actor_id: str, conductor: EnsembleConductor):
        self.actor_id = actor_id
        self.conductor = conductor

    def handle_contention(
        self,
        task_id: str,
        now: Optional[float] = None,
    ) -> Optional[str]:
        """
        Receives 409 Conflict. Requests a conductor nudge and returns the next task ID to pivot to.
        """
        nudge = self.conductor.observe_contention_and_nudge(
            contested_task_id=task_id,
            blocked_actor_id=self.actor_id,
            now=now,
        )
        if nudge and nudge.suggested_alternative_task_ids:
            return nudge.suggested_alternative_task_ids[0]
        return None
