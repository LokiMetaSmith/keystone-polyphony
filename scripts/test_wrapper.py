import sys
import subprocess
from lock_utils import acquire_lock, release_lock


def main():
    acquire_lock()
    try:
        # Run tests
        print(">>> Running serialized health checks...")
        result = subprocess.run(["./scripts/run-tests.sh"])
        sys.exit(result.returncode)
    finally:
        release_lock()


if __name__ == "__main__":
    main()
