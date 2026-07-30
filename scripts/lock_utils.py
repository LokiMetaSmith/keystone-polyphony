import os
import time

# A machine-wide lock file so multiple agents in different worktrees synchronize on the same machine.
LOCK_FILE = "/tmp/polyphony_build.lock"

# We keep track of whether we own the lock so we don't accidentally release someone else's.
owns_lock = False


def check_pid_alive(pid):
    """Check if a process is running on this local machine."""
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def acquire_lock():
    """Acquire the local PID-based lock atomically, waiting if necessary."""
    global owns_lock
    print(">>> Acquiring local build lock...")
    while True:
        try:
            # Try to create the file exclusively
            fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            # If successful, write our PID
            with os.fdopen(fd, "w") as f:
                f.write(str(os.getpid()))
            owns_lock = True
            print(">>> Acquired local build lock.")
            break
        except FileExistsError:
            # The file exists. Let's see if the lock is stale.
            try:
                with open(LOCK_FILE, "r") as f:
                    content = f.read().strip()
                    if not content:
                        # Empty lock file, maybe being written. We will wait.
                        raise ValueError("Empty lock file")
                    lock_pid = int(content)
                if check_pid_alive(lock_pid):
                    print(f"    Lock is held by PID {lock_pid}. Waiting...")
                    time.sleep(5)
                else:
                    print(
                        f"    Found stale lock from dead PID {lock_pid}. Reclaiming..."
                    )
                    try:
                        os.remove(LOCK_FILE)
                    except OSError:
                        pass
            except (ValueError, IOError):
                # Could not read the lock file properly, just wait and retry
                time.sleep(1)


def release_lock():
    """Release the local lock, but only if we own it."""
    global owns_lock
    if owns_lock:
        try:
            os.remove(LOCK_FILE)
            owns_lock = False
            print(">>> Released local build lock.")
        except OSError:
            pass
