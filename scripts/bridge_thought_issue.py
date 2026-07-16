import asyncio
import os
import sys

# Get the directory containing this script
current_dir = os.path.dirname(os.path.abspath(__file__))
# Add parent directory of current_dir to sys.path so we can import 'src'
sys.path.append(os.path.dirname(current_dir))

from src.liminal_bridge.mesh import LiminalMesh
from src.liminal_bridge.architect import Architect


async def main():
    swarm_key = os.getenv("SWARM_KEY", "KEYSTONE-POLYPHONY-UPSTREAM")
    mesh = LiminalMesh(secret_key=swarm_key)
    architect = Architect()

    if not architect.is_configured:
        print("Architect not configured.")
        return

    await mesh.start()

    print("Bridge started. Monitoring thoughts for #proposal...")

    processed_thoughts = set()

    try:
        while True:
            for node_id, thought in mesh.thoughts.items():
                content = (
                    thought.get("content", "") if isinstance(thought, dict) else thought
                )
                if (
                    isinstance(content, str)
                    and "#proposal" in content
                    and node_id not in processed_thoughts
                ):
                    print(f"Found proposal from {node_id}: {content[:50]}...")
                    refined_content = await architect.refine_issue(content)

                    # Save locally
                    filename = f"proposal_{node_id[:8]}.md"
                    with open(filename, "w") as f:
                        f.write(refined_content)

                    print(f"Refined issue saved to {filename}")
                    processed_thoughts.add(node_id)

            await asyncio.sleep(5)
    except KeyboardInterrupt:
        pass
    finally:
        await mesh.stop()


if __name__ == "__main__":
    asyncio.run(main())
