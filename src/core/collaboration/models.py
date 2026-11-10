"""Data models and type definitions for durable, fenced collaboration."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import time
import hashlib
import json


class TaskStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    INTEGRATING = "integrating"
    REVIEWING = "reviewing"
    ACCEPTED = "accepted"
    HELD = "held"
    REJECTED = "rejected"
    EXHAUSTED = "exhausted"


class AttemptStatus(str, Enum):
    ASSIGNED = "assigned"
    RUNNING = "running"
    SUBMITTED = "submitted"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"
    FAILED = "failed"
    EXPIRED = "expired"


class ReviewVerdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    HOLD = "HOLD"


class HostSignalType(str, Enum):
    SCALE_UP = "SCALE_UP"
    SPAWN_REVIEWER = "SPAWN_REVIEWER"
    IDLE_DRAIN = "IDLE_DRAIN"
    ESCALATE_TRIAGE = "ESCALATE_TRIAGE"


class HostSignalStatus(str, Enum):
    PENDING = "PENDING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    FULFILLED = "FULFILLED"
    REJECTED = "REJECTED"


class ConductorLeaseStatus(str, Enum):
    ACTIVE = "ACTIVE"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"


@dataclass
class ResourceEnvelope:
    max_budget: float = 100.0
    settled_budget: float = 0.0
    in_flight_reserved_budget: float = 0.0
    max_attempts: int = 5
    attempt_count: int = 0

    def can_reserve(self, amount: float) -> bool:
        return (
            self.settled_budget + self.in_flight_reserved_budget + amount
        ) <= self.max_budget

    def reserve(self, amount: float) -> bool:
        if not self.can_reserve(amount):
            return False
        self.in_flight_reserved_budget += amount
        return True

    def settle(self, reserved_amount: float, actual_cost: float) -> None:
        self.in_flight_reserved_budget = max(
            0.0, self.in_flight_reserved_budget - reserved_amount
        )
        self.settled_budget += actual_cost

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_budget": self.max_budget,
            "settled_budget": self.settled_budget,
            "in_flight_reserved_budget": self.in_flight_reserved_budget,
            "max_attempts": self.max_attempts,
            "attempt_count": self.attempt_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResourceEnvelope":
        return cls(
            max_budget=float(data.get("max_budget", 100.0)),
            settled_budget=float(data.get("settled_budget", 0.0)),
            in_flight_reserved_budget=float(data.get("in_flight_reserved_budget", 0.0)),
            max_attempts=int(data.get("max_attempts", 5)),
            attempt_count=int(data.get("attempt_count", 0)),
        )


@dataclass
class TaskObjective:
    task_id: str
    title: str
    description: str
    baseline_sha: str
    acceptance_criteria: List[str]
    spec_revision: int = 1
    schema_version: int = 2
    status: TaskStatus = TaskStatus.OPEN
    envelope: ResourceEnvelope = field(default_factory=ResourceEnvelope)
    current_fence_token: int = 0
    current_assignment_id: Optional[str] = None
    active_attempt_id: Optional[str] = None
    accepted_candidate_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "baseline_sha": self.baseline_sha,
            "acceptance_criteria": self.acceptance_criteria,
            "spec_revision": self.spec_revision,
            "schema_version": self.schema_version,
            "status": self.status.value,
            "envelope": self.envelope.to_dict(),
            "current_fence_token": self.current_fence_token,
            "current_assignment_id": self.current_assignment_id,
            "active_attempt_id": self.active_attempt_id,
            "accepted_candidate_id": self.accepted_candidate_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskObjective":
        return cls(
            task_id=data["task_id"],
            title=data.get("title", ""),
            description=data.get("description", ""),
            baseline_sha=data.get("baseline_sha", ""),
            acceptance_criteria=data.get("acceptance_criteria", []),
            spec_revision=int(data.get("spec_revision", 1)),
            schema_version=int(data.get("schema_version", 2)),
            status=TaskStatus(data.get("status", TaskStatus.OPEN.value)),
            envelope=ResourceEnvelope.from_dict(data.get("envelope", {})),
            current_fence_token=int(data.get("current_fence_token", 0)),
            current_assignment_id=data.get("current_assignment_id"),
            active_attempt_id=data.get("active_attempt_id"),
            accepted_candidate_id=data.get("accepted_candidate_id"),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
        )


@dataclass
class AssignmentClaim:
    assignment_id: str
    task_id: str
    actor_id: str
    fence_token: int
    attempt_token: str
    reserved_cost: float
    lease_expires_at: float
    status: AttemptStatus = AttemptStatus.ASSIGNED
    created_at: float = field(default_factory=time.time)

    def is_expired(self, current_time: Optional[float] = None) -> bool:
        now = current_time if current_time is not None else time.time()
        return now > self.lease_expires_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assignment_id": self.assignment_id,
            "task_id": self.task_id,
            "actor_id": self.actor_id,
            "fence_token": self.fence_token,
            "attempt_token": self.attempt_token,
            "reserved_cost": self.reserved_cost,
            "lease_expires_at": self.lease_expires_at,
            "status": self.status.value,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AssignmentClaim":
        return cls(
            assignment_id=data["assignment_id"],
            task_id=data["task_id"],
            actor_id=data["actor_id"],
            fence_token=int(data["fence_token"]),
            attempt_token=data["attempt_token"],
            reserved_cost=float(data.get("reserved_cost", 0.0)),
            lease_expires_at=float(data["lease_expires_at"]),
            status=AttemptStatus(data.get("status", AttemptStatus.ASSIGNED.value)),
            created_at=float(data.get("created_at", time.time())),
        )


@dataclass
class ContributionSubmission:
    task_id: str
    assignment_id: str
    actor_id: str
    fence_token: int
    request_id: str
    diff_text: str
    candidate_sha: str
    actual_cost: float
    spec_revision: int
    baseline_sha: str
    receipt_id: str
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "assignment_id": self.assignment_id,
            "actor_id": self.actor_id,
            "fence_token": self.fence_token,
            "request_id": self.request_id,
            "diff_text": self.diff_text,
            "candidate_sha": self.candidate_sha,
            "actual_cost": self.actual_cost,
            "spec_revision": self.spec_revision,
            "baseline_sha": self.baseline_sha,
            "receipt_id": self.receipt_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContributionSubmission":
        return cls(
            task_id=data["task_id"],
            assignment_id=data["assignment_id"],
            actor_id=data["actor_id"],
            fence_token=int(data["fence_token"]),
            request_id=data["request_id"],
            diff_text=data["diff_text"],
            candidate_sha=data["candidate_sha"],
            actual_cost=float(data.get("actual_cost", 0.0)),
            spec_revision=int(data.get("spec_revision", 1)),
            baseline_sha=data.get("baseline_sha", ""),
            receipt_id=data["receipt_id"],
            created_at=float(data.get("created_at", time.time())),
        )


@dataclass
class CandidateReceipt:
    candidate_id: str
    task_id: str
    baseline_sha: str
    patch_sha: str
    spec_revision: int
    author_actor_id: str
    created_at: float = field(default_factory=time.time)

    @staticmethod
    def calculate_id(baseline_sha: str, patch_sha: str, spec_revision: int) -> str:
        data = f"{baseline_sha}:{patch_sha}:{spec_revision}".encode("utf-8")
        return hashlib.sha256(data).hexdigest()


@dataclass
class ReviewReceipt:
    review_id: str
    candidate_id: str
    task_id: str
    reviewer_actor_id: str
    verdict: ReviewVerdict
    blocking_findings: int
    spec_revision: int
    baseline_sha: str
    notes: str = ""
    is_valid: bool = True
    created_at: float = field(default_factory=time.time)


@dataclass
class ConductorLease:
    lease_id: str
    actor_id: str
    fence_token: int
    active_worker_count: int
    expires_at: float
    status: ConductorLeaseStatus = ConductorLeaseStatus.ACTIVE
    created_at: float = field(default_factory=time.time)

    def is_expired(self, current_time: Optional[float] = None) -> bool:
        now = current_time if current_time is not None else time.time()
        return now > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "actor_id": self.actor_id,
            "fence_token": self.fence_token,
            "active_worker_count": self.active_worker_count,
            "expires_at": self.expires_at,
            "status": (
                self.status.value
                if isinstance(self.status, ConductorLeaseStatus)
                else str(self.status)
            ),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConductorLease":
        return cls(
            lease_id=data["lease_id"],
            actor_id=data["actor_id"],
            fence_token=int(data["fence_token"]),
            active_worker_count=int(data.get("active_worker_count", 0)),
            expires_at=float(data["expires_at"]),
            status=ConductorLeaseStatus(
                data.get("status", ConductorLeaseStatus.ACTIVE.value)
            ),
            created_at=float(data.get("created_at", time.time())),
        )


@dataclass
class HostTelemetrySignal:
    signal_id: str
    emitted_by_actor: str
    signal_type: HostSignalType
    requested_worker_delta: int
    target_task_ids: List[str]
    unsettled_cost_snapshot: float
    rationale: str
    host_status: HostSignalStatus = HostSignalStatus.PENDING
    host_response_note: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "emitted_by_actor": self.emitted_by_actor,
            "signal_type": (
                self.signal_type.value
                if isinstance(self.signal_type, HostSignalType)
                else str(self.signal_type)
            ),
            "requested_worker_delta": self.requested_worker_delta,
            "target_task_ids": list(self.target_task_ids),
            "unsettled_cost_snapshot": self.unsettled_cost_snapshot,
            "rationale": self.rationale,
            "host_status": (
                self.host_status.value
                if isinstance(self.host_status, HostSignalStatus)
                else str(self.host_status)
            ),
            "host_response_note": self.host_response_note,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HostTelemetrySignal":
        target_tasks = data.get("target_task_ids", [])
        if isinstance(target_tasks, str):
            try:
                target_tasks = json.loads(target_tasks)
            except Exception:
                target_tasks = [target_tasks]
        return cls(
            signal_id=data["signal_id"],
            emitted_by_actor=data["emitted_by_actor"],
            signal_type=HostSignalType(data["signal_type"]),
            requested_worker_delta=int(data.get("requested_worker_delta", 0)),
            target_task_ids=target_tasks,
            unsettled_cost_snapshot=float(data.get("unsettled_cost_snapshot", 0.0)),
            rationale=data.get("rationale", ""),
            host_status=HostSignalStatus(
                data.get("host_status", HostSignalStatus.PENDING.value)
            ),
            host_response_note=data.get("host_response_note", ""),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
        )
