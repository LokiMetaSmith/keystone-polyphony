import sys
import subprocess
import argparse
from lock_utils import acquire_lock, release_lock


def run_command(cmd, abort_on_fail=True):
    """Run a shell command, printing its output."""
    print(f"    Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        if abort_on_fail:
            print(f"❌ Command failed: {' '.join(cmd)}")
            release_lock()
            sys.exit(result.returncode)
        return False
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Safely rebase, test, and push local branch to main queueing up local tests."
    )
    parser.add_argument(
        "--branch",
        default="main",
        help="The integration branch to land onto (default: main)",
    )
    args = parser.parse_args()

    branch = args.branch

    print(f">>> Queuing for safe land onto {branch}...")

    # We must acquire the lock BEFORE we fetch and rebase.
    # Otherwise, concurrent agents will rebase against the same initial main,
    # and the second one to finish tests will fail to push.
    acquire_lock()
    try:
        # Fetch latest to ensure we rebase against the true remote state
        run_command(["git", "fetch", "origin", branch])

        # Rebase onto the integration branch
        print(f">>> Rebasing current branch onto origin/{branch}...")
        rebase_success = run_command(
            ["git", "rebase", f"origin/{branch}"], abort_on_fail=False
        )

        if not rebase_success:
            print("❌ Rebase failed due to conflicts.")
            print(
                "    Aborting rebase. Please resolve conflicts manually and run `polyphony land` again."
            )
            subprocess.run(["git", "rebase", "--abort"])
            # release_lock will be called in finally
            sys.exit(1)

        # Run tests (call test script directly as we already hold the lock)
        print(">>> Running serialized health checks...")
        run_command(["./scripts/run-tests.sh"])

        # Push to the remote branch
        print(f">>> Pushing to origin/{branch}...")
        run_command(["git", "push", "origin", f"HEAD:{branch}"])
        print("✅ Land successful!")
    finally:
        release_lock()


if __name__ == "__main__":
    main()
