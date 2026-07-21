from contextlib import asynccontextmanager
import time
import os
import sys

# Assume we need to import LiminalMesh from liminal_bridge.
# Let's add the src directory to path just in case, though the caller might have it.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from liminal_bridge.mesh import LiminalMesh


class FileLockedError(Exception):
    """Raised when a file lock cannot be acquired because another agent holds it."""

    pass


@asynccontextmanager
async def polyphony_file_lock(
    filepath: str, mesh: LiminalMesh = None, timeout: float = 2.0
):
    """
    Context manager to safely acquire and release a granular file lock across the swarm.

    If the lock is held by another agent, raises a FileLockedError. This allows the
    agent tool calling it to catch the error, generate a diff, and broadcast a backpressure
    intent (e.g. via mesh.ping).
    """
    if mesh is None:
        raise ValueError("LiminalMesh instance must be provided.")

    # Attempt to acquire the baton
    success = await mesh.acquire_baton(filepath, timeout=timeout)
    if not success:
        owner = mesh.batons.get(filepath, "unknown")
        raise FileLockedError(f"File '{filepath}' is currently locked by {owner}.")

    try:
        yield
    finally:
        # Release the baton once editing is complete
        await mesh.release_baton(filepath)
