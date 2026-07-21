import asyncio
import os
import sys
import argparse

sys.path.insert(0, os.path.abspath("src"))
from liminal_bridge.mesh import LiminalMesh
from liminal_bridge.auth import get_or_create_swarm_key


async def main():
    parser = argparse.ArgumentParser(description="Manage granular file locks")
    parser.add_argument(
        "action", choices=["acquire", "release"], help="Action to perform"
    )
    parser.add_argument("filepath", type=str, help="The file path to lock or unlock")

    args = parser.parse_args()

    swarm_key = get_or_create_swarm_key()
    mesh = LiminalMesh(secret_key=swarm_key)

    await mesh.start()
    try:
        if args.action == "acquire":
            success = await mesh.acquire_baton(args.filepath)
            if success:
                print(f"SUCCESS: Baton acquired for {args.filepath}")
            else:
                owner = mesh.batons.get(args.filepath, "unknown")
                print(f"DENIED: {args.filepath} is currently locked by {owner}.")
                sys.exit(1)
        elif args.action == "release":
            await mesh.release_baton(args.filepath)
            print(f"SUCCESS: Baton released for {args.filepath}")
    finally:
        await mesh.stop()


if __name__ == "__main__":
    asyncio.run(main())
