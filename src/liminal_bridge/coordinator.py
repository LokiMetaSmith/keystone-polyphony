"""Compatibility shim for Durable Collaboration Authority.

The canonical implementation has been unified into `src.core.collaboration.authority`.
This module re-exports all symbols to preserve backward compatibility.
"""

from src.core.collaboration.authority import (
    Conflict,
    canonical,
    digest,
    positive,
    immutable_revision,
    managed_task,
    Coordinator,
    select_task,
)

__all__ = [
    "Conflict",
    "canonical",
    "digest",
    "positive",
    "immutable_revision",
    "managed_task",
    "Coordinator",
    "select_task",
]
