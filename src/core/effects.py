from typing import Any


class BaseEffect:
    """Base class for all purely declarative side effects returned by Isolates."""

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"


# Create Effect alias for drop-in compatibility with other systems
Effect = BaseEffect


class SendMessageEffect(BaseEffect):
    """Effect to send a message to another mailbox/isolate."""

    def __init__(
        self,
        target_mailbox_id: str = None,
        message: Any = None,
        target: str = None,
        payload: Any = None,
    ):
        # Support both target_mailbox_id/message and target/payload signatures
        self.target_mailbox_id = target if target is not None else target_mailbox_id
        self.message = payload if payload is not None else message

    @property
    def target(self) -> str:
        return self.target_mailbox_id

    @property
    def payload(self) -> Any:
        return self.message

    def __repr__(self) -> str:
        return f"SendMessageEffect(target={self.target_mailbox_id}, message={self.message})"


class PersistStateEffect(BaseEffect):
    """Effect to persist the current state out-of-band."""

    def __init__(self, state_delta: Any):
        self.state_delta = state_delta

    def __repr__(self) -> str:
        return f"PersistStateEffect(state_delta={self.state_delta})"


class LogEffect(BaseEffect):
    """Effect to perform a logging action."""

    def __init__(self, *args, **kwargs):
        # Support positional arguments: (level, message) or (message, level)
        # Support keyword arguments: level, message
        level = kwargs.get("level")
        message = kwargs.get("message")

        standard_levels = {"INFO", "WARNING", "ERROR", "DEBUG", "CRITICAL", "WARN"}

        if len(args) == 2:
            arg0, arg1 = args
            if str(arg0).upper() in standard_levels:
                level = arg0
                message = arg1
            elif str(arg1).upper() in standard_levels:
                message = arg0
                level = arg1
            else:
                level = arg0
                message = arg1
        elif len(args) == 1:
            arg0 = args[0]
            if str(arg0).upper() in standard_levels:
                level = arg0
            else:
                message = arg0

        # Resolve defaults
        self.level = level if level is not None else "INFO"
        self.message = message if message is not None else ""

    def __repr__(self) -> str:
        return f"LogEffect(level={self.level}, message={self.message})"


class ScheduleTimeoutEffect(BaseEffect):
    """Effect to schedule a delayed message to ourselves or another target."""

    def __init__(self, delay_ticks: int, message: Any, target_mailbox_id: str = ""):
        self.delay_ticks = delay_ticks
        self.message = message
        self.target_mailbox_id = target_mailbox_id

    def __repr__(self) -> str:
        return f"ScheduleTimeoutEffect(delay_ticks={self.delay_ticks}, target={self.target_mailbox_id})"
