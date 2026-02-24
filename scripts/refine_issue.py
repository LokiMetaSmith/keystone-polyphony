import argparse
import asyncio
import os
import sys

# Get the directory containing this script
current_dir = os.path.dirname(os.path.abspath(__file__))
# Add parent directory of current_dir to sys.path so we can import 'src'
sys.path.append(os.path.dirname(current_dir))

try:
    from src.liminal_bridge.architect import Architect
except ImportError:
    print("Error: Could not import Architect from src.liminal_bridge.architect")
    sys.exit(1)


async def main():
    parser = argparse.ArgumentParser(
        description="Refine a GitHub issue file using Architect."
    )
    parser.add_argument("filepath", help="Path to the issue markdown file.")
    args = parser.parse_args()

    if not os.path.exists(args.filepath):
        print(f"Error: File {args.filepath} not found.")
        sys.exit(1)

    with open(args.filepath, "r") as f:
        content = f.read()

    architect = Architect()

    # Check if Architect is configured
    if not architect.client and not architect.google_model:
        print(
            "Warning: Architect not configured (missing API key or package). Skipping refinement."
        )
        sys.exit(0)

    print(f"Refining issue: {args.filepath}...")
    try:
        refined_content = await architect.refine_issue(content)

        # Add the refinement marker if not present
        if "<!-- triage-refined: architect -->" not in refined_content:
            refined_content += "\n\n<!-- triage-refined: architect -->"

        with open(args.filepath, "w") as f:
            f.write(refined_content)

        print(f"Successfully refined {args.filepath}")

    except Exception as e:
        print(f"Error refining issue: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
