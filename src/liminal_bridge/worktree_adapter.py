"""Bounded cooperative POSIX workers with an unreaped PID as group ownership.

The main child is retained with waitid(WNOWAIT) until process-group cleanup.
A restarted supervisor reports unknown and never signals remembered PIDs.
"""

import asyncio
import os
from pathlib import Path
import re
import signal
import sqlite3
import subprocess
import tempfile
import time

from .coordinator import Conflict, positive


class GitWorktreeAdapter:
    def __init__(self, repository, root):
        self.repository = Path(repository).resolve()
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.running = {}
        self.watchers = {}
        self.results = {}
        self.cancel_requests = set()

    def query_capabilities(self):
        return {
            "isolation": "working_files_only",
            "execution_limits": "live_supervisor_process_group",
            "recovery": "durable_worktree_unknown_process_after_restart",
            "termination_confirmation": hasattr(os, "WNOWAIT")
            and callable(getattr(os, "waitid", None))
            and Path("/proc/self/stat").exists(),
            "cost": None,
            "platform": "linux_proc_waitid",
        }

    def validate_execution(self):
        if (
            os.name != "posix"
            or not self.query_capabilities()["termination_confirmation"]
        ):
            raise ValueError("adapter requires waitid(WNOWAIT) and Linux procfs")

    def _path(self, attempt_id):
        if not re.fullmatch(r"[a-f0-9]{32}", attempt_id):
            raise ValueError("invalid attempt id")
        return self.root / attempt_id

    def _prepare(self, path, base):
        sha = subprocess.check_output(
            [
                "git",
                "-C",
                str(self.repository),
                "rev-parse",
                "--verify",
                f"{base}^{{commit}}",
            ],
            text=True,
            timeout=30,
        ).strip()
        subprocess.run(
            [
                "git",
                "-C",
                str(self.repository),
                "worktree",
                "add",
                "--detach",
                str(path),
                sha,
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        return sha

    async def launch(
        self,
        attempt_id,
        base,
        command,
        seconds,
        env=None,
        input_text=None,
        before_spawn=None,
    ):
        positive(seconds)
        path = self._path(attempt_id)
        if path.exists() or attempt_id in self.watchers or attempt_id in self.results:
            raise Conflict("attempt already launched; observe before retry")
        self.validate_execution()
        if not command or not all(isinstance(arg, str) for arg in command):
            raise ValueError("command must be a nonempty argv list")
        if input_text is not None and not isinstance(input_text, str):
            raise ValueError("approved input must be text")
        deadline = time.monotonic() + seconds
        # Reserve the attempt in memory before yielding during Git preparation.
        self.watchers[attempt_id] = None
        log = None
        process = None
        try:
            sha = await asyncio.to_thread(self._prepare, path, base)
            if attempt_id in self.cancel_requests:
                raise Conflict("attempt cancelled before launch")
            if time.monotonic() >= deadline:
                raise Conflict("attempt execution limit expired during preparation")
            if before_spawn:
                before_spawn()
            fd = os.open(
                self.root / f"{attempt_id}.log",
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
            log = os.fdopen(fd, "wb")
            # No asyncio child watcher may reap this PID before group cleanup.
            # Anonymous stdin also avoids blocking on a full pipe during launch.
            with tempfile.TemporaryFile() as approved_input:
                if input_text is not None:
                    approved_input.write(input_text.encode())
                approved_input.seek(0)
                if time.monotonic() >= deadline:
                    raise Conflict("attempt execution limit expired before spawn")
                process = subprocess.Popen(
                    command,
                    cwd=path,
                    env=env,
                    start_new_session=True,
                    stdin=approved_input,
                    stdout=log,
                    stderr=log,
                )
            self.running[attempt_id] = process
            self.watchers[attempt_id] = asyncio.create_task(
                self._supervise(attempt_id, process, deadline, log)
            )
        except BaseException:
            if process is not None:
                # A failed supervisor registration must not orphan a spawned
                # child or describe it as a launch that never happened.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.watchers.pop(attempt_id, None)
                self.running[attempt_id] = process
                self.results[attempt_id] = {
                    "state": "unknown",
                    "termination_confirmed": False,
                    "returncode": None,
                    "cost": None,
                }
                if self._group_dead(process.pid):
                    self.running.pop(attempt_id, None)
                    self.results[attempt_id] = {
                        "state": "exited",
                        "termination_confirmed": True,
                        "returncode": process.wait(),
                        "cost": None,
                    }
                log.close()
                raise
            if log:
                log.close()
            # This invocation did not spawn a child. Unknown prior launches are
            # rejected above, before installing this fresh preparation claim.
            self.results[attempt_id] = {
                "state": "exited",
                "termination_confirmed": True,
                "returncode": None,
                "cost": None,
                "not_started": True,
            }
            self.watchers.pop(attempt_id, None)
            raise
        return {"attempt": attempt_id, "base": sha, "state": "running", "cost": None}

    def _group_dead(self, pgid):
        # The unreaped leader keeps the PGID allocated during this inspection.
        # Zombies cannot write files; live or uninspectable members mean unknown.
        try:
            entries = list(Path("/proc").iterdir())
        except OSError:
            return False
        for entry in entries:
            if not entry.name.isdecimal():
                continue
            try:
                fields = (entry / "stat").read_text().rpartition(")")[2].split()
                if int(fields[2]) == pgid and fields[0] not in {"Z", "X"}:
                    return False
            except (FileNotFoundError, ProcessLookupError):
                continue
            except (OSError, ValueError, IndexError):
                return False
        return True

    async def _finish(self, aid, process, state):
        self.running.pop(aid, None)  # No signal path may retain a reaped PID.
        returncode = await asyncio.to_thread(process.wait)
        self.results[aid] = {
            "state": state,
            "termination_confirmed": True,
            "returncode": returncode,
            "cost": None,
        }

    async def _supervise(self, aid, process, deadline, log):
        state = "exited"
        owned = True
        try:
            while True:
                # CPython returns None under WNOHANG while the child is alive.
                exited = os.waitid(
                    os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT
                )
                if exited is not None or aid in self.cancel_requests:
                    break
                if time.monotonic() >= deadline:
                    state = "timed_out"
                    break
                await asyncio.sleep(min(0.02, max(0, deadline - time.monotonic())))
        except ChildProcessError:
            # Another actor reaped it: PID ownership is no longer provable.
            owned = False
        finally:
            if owned:
                # The main child is alive or an unreaped zombie, so this PGID
                # cannot have been recycled into another job's process group.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                settle = time.monotonic() + 1
                while not await asyncio.to_thread(self._group_dead, process.pid):
                    if time.monotonic() >= settle:
                        self.results[aid] = {
                            "state": "unknown",
                            "termination_confirmed": False,
                            "returncode": None,
                            "cost": None,
                            "pending_state": state,
                        }
                        break
                    await asyncio.sleep(0.02)
                else:
                    await self._finish(aid, process, state)
            else:
                self.running.pop(aid, None)
                self.results[aid] = {
                    "state": "unknown",
                    "termination_confirmed": False,
                    "returncode": None,
                    "cost": None,
                }
            log.close()

    async def observe(self, attempt_id):
        self._path(attempt_id)
        if attempt_id in self.results:
            result = self.results[attempt_id]
            process = self.running.get(attempt_id)
            if not result["termination_confirmed"] and process is not None:
                if await asyncio.to_thread(self._group_dead, process.pid):
                    # Another observer may have completed it while inspecting.
                    if self.running.get(attempt_id) is process:
                        await self._finish(
                            attempt_id, process, result.get("pending_state", "exited")
                        )
            return self.results[attempt_id]
        if attempt_id in self.running:
            return {"state": "running", "termination_confirmed": False, "cost": None}
        # Includes Git preparation: watchers[attempt_id] is a None placeholder.
        return {"state": "unknown", "termination_confirmed": False, "cost": None}

    async def cancel(self, attempt_id):
        self._path(attempt_id)
        if attempt_id in self.results:
            return self.results[attempt_id]
        self.cancel_requests.add(attempt_id)
        watcher = self.watchers.get(attempt_id)
        if watcher is not None:
            # Only the owning supervisor signals the group; retries only wait.
            await asyncio.shield(watcher)
        return await self.observe(attempt_id)

    def patch(self, attempt_id, base):
        path = self._path(attempt_id)
        if not self.results.get(attempt_id, {}).get("termination_confirmed"):
            raise Conflict("cannot capture a patch while termination is unknown")
        subprocess.run(
            ["git", "-C", str(path), "add", "--all"],
            check=True,
            capture_output=True,
            timeout=30,
        )
        return subprocess.check_output(
            [
                "git",
                "-C",
                str(path),
                "diff",
                "--cached",
                "--binary",
                "--full-index",
                base,
                "--",
            ],
            timeout=30,
        ).decode()

    async def wait(self, attempt_id):
        watcher = self.watchers.get(attempt_id)
        if watcher is None:
            return await self.observe(attempt_id)
        await asyncio.shield(watcher)
        return await self.observe(attempt_id)


async def run_attempt(
    store, adapter, attempt, base, command, env=None, input_text=None
):
    """Preserve work before publishing a completed execution to task selectors."""
    aid = attempt["id"]
    try:
        store.execution_permission(aid, attempt["worker"])
        handle = await adapter.launch(
            aid,
            base,
            command,
            store.remaining_seconds(aid, attempt["worker"]),
            env=env,
            input_text=input_text,
            before_spawn=lambda: store.execution_permission(aid, attempt["worker"]),
        )
    except Exception:
        state = await adapter.observe(aid)
        # A failed launch can still have spawned a child and produced work.
        # Only explicit proof of no spawn permits release without capture.
        unlaunched = state.get("not_started") is True
        store.observe(aid, "exited" if unlaunched else "unknown", unlaunched)
        raise
    try:
        store.observe(aid, "running")
    except sqlite3.Error:
        pass  # The live adapter still enforces the previously approved limit.
    # Wait failures leave the reservation held; capture's finally is not entered.
    result = await adapter.wait(aid)
    if not result["termination_confirmed"]:
        store.observe(aid, "unknown")
        raise Conflict("execution termination unknown")
    # Capture failure must keep the authority reservation held. A local process
    # exit is not permission to spend another attempt before its work is saved.
    patch = await asyncio.to_thread(adapter.patch, aid, handle["base"])
    artifact = store.save_work(aid, attempt["worker"], patch)
    try:
        candidate = store.candidate(aid, attempt["worker"], handle["base"], artifact)
        if result["returncode"]:
            store.problem(
                aid,
                attempt["worker"],
                f"execution {result['state']}; exit {result['returncode']}",
            )
        return {"execution": result, "candidate": candidate}
    finally:
        store.observe(aid, result["state"], True)
