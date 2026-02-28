#!/usr/bin/env python3
import asyncio
import json
import os
import sys
import glob

# Add parent directory of current_dir to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(current_dir))

try:
    from src.liminal_bridge.architect import Architect
except ImportError:
    print("Error: Could not import Architect from src.liminal_bridge.architect")
    sys.exit(1)


async def main():
    triage_agents = os.getenv("TRIAGE_AGENTS", "")
    if "architect" not in triage_agents.lower():
        print("Architect not enabled in TRIAGE_AGENTS. Skipping deduplication.")
        # If architect is not enabled, we do nothing.
        return

    issues_dir = ".github/issues"
    issue_files = glob.glob(os.path.join(issues_dir, "*.md"))

    if not issue_files:
        print("No issues found to deduplicate.")
        return

    print(f"Found {len(issue_files)} issues. Analyzing for duplicates...")

    issues = {}
    for filepath in issue_files:
        filename = os.path.basename(filepath)
        with open(filepath, "r") as f:
            issues[filename] = f.read()

    architect = Architect()

    # Check if Architect is configured
    if not architect.is_configured:
        print("Architect not configured. Skipping deduplication.")
        return

    try:
        response = await architect.deduplicate_backlog(issues)
        # Clean up response if it contains markdown code blocks
        if response.startswith("```json"):
            response = response.replace("```json", "").replace("```", "")
        elif response.startswith("```"):
            response = response.replace("```", "")

        duplicates_map = json.loads(response)
    except Exception as e:
        print(f"Error parsing deduplication response: {e}")
        # print(f"Response was: {response}") # May be undefined if error before assignment
        return

    if not duplicates_map:
        print("No duplicates found.")
        return

    for primary, dups in duplicates_map.items():
        # Security check: Ensure filename is safe (no path traversal)
        if os.path.basename(primary) != primary:
            print(
                f"Warning: Primary filename '{primary}' contains path traversal characters. Skipping."
            )
            continue

        primary_path = os.path.join(issues_dir, primary)
        if not os.path.exists(primary_path):
            print(f"Warning: Primary issue {primary} not found. Skipping.")
            continue

        if not dups:
            continue

        print(f"Merging duplicates into {primary}: {dups}")

        with open(primary_path, "a") as f:
            f.write("\n\n## Merged Duplicates\n")
            for dup in dups:
                # Security check
                if os.path.basename(dup) != dup:
                    print(
                        f"Warning: Duplicate filename '{dup}' contains path traversal characters. Skipping."
                    )
                    continue

                dup_path = os.path.join(issues_dir, dup)
                if not os.path.exists(dup_path):
                    continue

                with open(dup_path, "r") as df:
                    content = df.read()
                    f.write(f"\n### From {dup}\n\n{content}\n")

                os.remove(dup_path)
                print(f"Deleted duplicate: {dup}")


if __name__ == "__main__":
    asyncio.run(main())
