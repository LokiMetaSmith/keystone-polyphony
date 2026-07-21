import asyncio
import os
import sys
import uuid
import json

sys.path.insert(0, os.path.abspath("src"))
from liminal_bridge.mesh import LiminalMesh
from liminal_bridge.auth import get_or_create_swarm_key

# Heuristics for Megafile Flagging
MAX_LINES = 1000
MAX_SIZE_BYTES = 50 * 1024  # 50KB


async def flag_megafile(filepath: str):
    if not os.path.exists(filepath):
        print(f"❌ ERROR: File '{filepath}' does not exist.")
        sys.exit(1)

    size = os.path.getsize(filepath)
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        lines = sum(1 for _ in f)

    if size <= MAX_SIZE_BYTES and lines <= MAX_LINES:
        print(
            f"File '{filepath}' is {lines} lines and {size} bytes. This does not exceed Megafile thresholds."
        )
        print(f"(Thresholds: >{MAX_LINES} lines OR >{MAX_SIZE_BYTES} bytes)")

        # Optionally allow forced flagging? For now we just return
        print("Not flagging.")
        sys.exit(0)

    print(f"Flagging '{filepath}' as a Megafile. Size: {size} bytes, Lines: {lines}.")

    swarm_key = get_or_create_swarm_key()
    mesh = LiminalMesh(secret_key=swarm_key)
    await mesh.start()

    try:
        # Create Refactor Task
        task = {
            "id": str(uuid.uuid4()),
            "title": f"Refactor Megafile: {filepath}",
            "description": f"The file '{filepath}' exceeds the Megafile threshold ({lines} lines, {size} bytes). Please decompose this file into smaller modules.",
            "owner": None,
            "status": "todo",
            "priority": "high",
            "required": [
                "refactor"
            ],  # Ensure only agents with refactor capability can claim
        }

        # Add to swarm backlog
        await mesh.update_set("swarm_backlog", json.dumps(task), urgency="high")

        # Broadcast thought about flagging
        await mesh.share_thought(
            f"Flagged '{filepath}' as a Megafile. Added refactor task {task['id'][:8]}.",
            urgency="high",
        )

        print(
            f"SUCCESS: Megafile flagged and task {task['id'][:8]} added to swarm backlog."
        )
    finally:
        await mesh.stop()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python flag_megafile.py <filepath>")
        sys.exit(1)

    filepath = sys.argv[1]
    asyncio.run(flag_megafile(filepath))
