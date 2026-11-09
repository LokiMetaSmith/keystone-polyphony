"""Portable execution contract and deterministic adapter with fault-injection hooks."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional, Tuple, Callable
import time
import uuid


class IsolationLevel(str, Enum):
    IN_PROCESS = "in_process"
    WORKTREE = "worktree"
    CONTAINER = "container"
    VM = "vm"


@dataclass
class AttemptLimits:
    timeout_seconds: float = 300.0
    max_memory_mb: int = 512
    max_cost: float = 10.0


@dataclass
class AttemptHandle:
    handle_id: str
    task_id: str
    attempt_id: str
    fence_token: int
    actor_id: str
    baseline_ref: str
    limits: AttemptLimits
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass
class AttemptObservation:
    handle_id: str
    status: str
    resource_consumption: float
    output: Optional[str] = None
    diff_text: Optional[str] = None
    error: Optional[str] = None


class BaseExecutionAdapter(ABC):
    """Abstract execution adapter interface satisfying the portable execution contract."""

    @abstractmethod
    def launch(
        self,
        task_id: str,
        attempt_id: str,
        fence_token: int,
        actor_id: str,
        baseline_ref: str,
        limits: Optional[AttemptLimits] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AttemptHandle:
        pass

    @abstractmethod
    def observe(self, handle: AttemptHandle) -> AttemptObservation:
        pass

    @abstractmethod
    def cancel(self, handle: AttemptHandle) -> Tuple[bool, float]:
        """Returns (termination_confirmed, settled_cost)."""
        pass

    @abstractmethod
    def query_capabilities(self) -> Dict[str, Any]:
        pass


class DeterministicExecutionAdapter(BaseExecutionAdapter):
    """In-memory deterministic execution adapter with programmatic fault-injection hooks."""

    def __init__(self):
        self.attempts: Dict[str, Dict[str, Any]] = {}
        # Fault injection hooks
        self.pause_before_submit: bool = False
        self.simulate_pre_reply_crash: bool = False
        self.simulate_partition: bool = False
        self.simulate_worker_disappearance: bool = False
        self.fail_launch: bool = False
        self.on_launch_callback: Optional[Callable[[AttemptHandle], None]] = None

    def query_capabilities(self) -> Dict[str, Any]:
        return {
            "isolation_level": IsolationLevel.IN_PROCESS.value,
            "supports_cancellation": True,
            "supports_resource_limiting": True,
            "deterministic_simulation": True,
        }

    def launch(
        self,
        task_id: str,
        attempt_id: str,
        fence_token: int,
        actor_id: str,
        baseline_ref: str,
        limits: Optional[AttemptLimits] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AttemptHandle:
        if self.fail_launch:
            raise RuntimeError("Fault injection: launch failed")

        handle_id = f"hnd_{uuid.uuid4().hex[:12]}"
        limits = limits or AttemptLimits()
        handle = AttemptHandle(
            handle_id=handle_id,
            task_id=task_id,
            attempt_id=attempt_id,
            fence_token=fence_token,
            actor_id=actor_id,
            baseline_ref=baseline_ref,
            limits=limits,
            metadata=metadata or {},
        )

        self.attempts[handle_id] = {
            "handle": handle,
            "status": "running",
            "consumption": 1.0,
            "diff_text": "",
            "terminated": False,
        }

        if self.on_launch_callback:
            self.on_launch_callback(handle)

        return handle

    def set_attempt_output(
        self, handle: AttemptHandle, diff_text: str, consumption: float = 2.0
    ) -> None:
        if handle.handle_id in self.attempts:
            self.attempts[handle.handle_id]["diff_text"] = diff_text
            self.attempts[handle.handle_id]["consumption"] = consumption
            self.attempts[handle.handle_id]["status"] = "completed"

    def observe(self, handle: AttemptHandle) -> AttemptObservation:
        if self.simulate_partition:
            return AttemptObservation(
                handle_id=handle.handle_id,
                status="unreachable",
                resource_consumption=0.0,
                error="Simulated network partition",
            )

        attempt = self.attempts.get(handle.handle_id)
        if not attempt:
            return AttemptObservation(
                handle_id=handle.handle_id,
                status="unknown",
                resource_consumption=0.0,
                error="Attempt handle not found",
            )

        return AttemptObservation(
            handle_id=handle.handle_id,
            status=attempt["status"],
            resource_consumption=attempt["consumption"],
            diff_text=attempt.get("diff_text"),
        )

    def cancel(self, handle: AttemptHandle) -> Tuple[bool, float]:
        attempt = self.attempts.get(handle.handle_id)
        if not attempt:
            return True, 0.0

        if self.simulate_worker_disappearance:
            # Termination cannot be confirmed
            attempt["status"] = "unknown_disappeared"
            return False, attempt["consumption"]

        attempt["status"] = "cancelled"
        attempt["terminated"] = True
        return True, attempt["consumption"]
