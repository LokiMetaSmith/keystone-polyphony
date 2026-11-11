"""Public authority conflict type shared by canonical operations."""


class Conflict(ValueError):
    """A precondition failed; retry only after observing new state."""
