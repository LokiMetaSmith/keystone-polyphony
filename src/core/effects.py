from dataclasses import dataclass
from typing import Any

class BaseEffect:
    """Base class for all purely declarative side effects returned by Isolates."""
    pass

@dataclass(frozen=True)
class SendMessageEffect(BaseEffect):
    """Effect to send a message to another mailbox/isolate."""
    target_mailbox_id: str
    message: Any

@dataclass(frozen=True)
class PersistStateEffect(BaseEffect):
    """Effect to persist the current state out-of-band."""
    state_delta: Any

@dataclass(frozen=True)
class LogEffect(BaseEffect):
    """Effect to perform a logging action."""
    level: str  # e.g., "INFO", "WARNING", "ERROR", "DEBUG"
    message: str

@dataclass(frozen=True)
class ScheduleTimeoutEffect(BaseEffect):
    """Effect to schedule a delayed message to ourselves or another target."""
    delay_ticks: int
    message: Any
    target_mailbox_id: str = ""  # Default empty means self/current mailbox
