"""Bounded local child processes in Git worktrees; not a host sandbox.

A restarted supervisor reports unknown rather than signalling possibly reused PIDs.
Only the live supervisor can confirm exit. Worktrees/logs remain for recovery.
"""

import asyncio
import os
from pathlib import Path
import re
import signal
import sqlite3
import subprocess
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
            "termination_confirmation": True,
            "cost": None,
            "platform": "posix",
        }

    def _path(self, attempt_id):
        if not re.fullmatch(r"[a-f0-9]{32}", attempt_id):
            raise ValueError("invalid attempt id")
        return self.root / attempt_id

    async def launch(
        self, attempt_id, base, command, seconds, env=None, input_text=None
    ):
        positive(seconds)
        if attempt_id in self.cancel_requests:
            raise Conflict("attempt was cancelled before launch")
        path = self._path(attempt_id)
        if path.exists() or attempt_id in self.running:
            raise Conflict("attempt already launched; observe before retry")
        if os.name != "posix":
            raise ValueError("prototype adapter requires POSIX process groups")
        if not command or not all(isinstance(arg, str) for arg in command):
            raise ValueError("command must be a nonempty argv list")
        # Resolve a commit before using it as a worktree argument.
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
        )
        log = open(self.root / f"{attempt_id}.log", "wb")
        os.chmod(log.name, 0o600)
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=path,
                env=env,
                start_new_session=True,
                stdin=(
                    asyncio.subprocess.PIPE
                    if input_text is not None
                    else asyncio.subprocess.DEVNULL
                ),
                stdout=log,
                stderr=log,
            )
        except BaseException:
            log.close()
            raise
        self.running[attempt_id] = process
        if attempt_id in self.cancel_requests:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self.watchers[attempt_id] = asyncio.create_task(
            self._supervise(attempt_id, process, seconds, log, input_text)
        )
        return {"attempt": attempt_id, "base": sha, "state": "running", "cost": None}

    async def _supervise(self, aid, process, seconds, log, input_text):
        state = "exited"
        try:
            # communicate drains stdin; stdout/stderr go to durable local log.
            await asyncio.wait_for(
                process.communicate(
                    None if input_text is None else input_text.encode()
                ),
                timeout=seconds,
            )
        except asyncio.TimeoutError:
            state = "timed_out"
        finally:
            # The main child can exit while descendants continue. Kill its group
            # before confirming termination, even on an ordinary successful exit.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()
            # Descendants may escape their group: this is cooperative execution,
            # never a security isolation guarantee (documented capability).
            self.results[aid] = {
                "state": state,
                "termination_confirmed": True,
                "returncode": process.returncode,
                "cost": None,
            }
            log.close()

    async def observe(self, attempt_id):
        self._path(attempt_id)
        if attempt_id in self.results:
            return self.results[attempt_id]
        if attempt_id in self.running:
            return {"state": "running", "termination_confirmed": False, "cost": None}
        return {"state": "unknown", "termination_confirmed": False, "cost": None}

    async def cancel(self, attempt_id):
        self._path(attempt_id)
        self.cancel_requests.add(attempt_id)
        process = self.running.get(attempt_id)
        if process is None:
            return {"state": "unknown", "termination_confirmed": False, "cost": None}
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        # Wait for supervisor to reap the main child before releasing reservation.
        await self.watchers[attempt_id]
        return await self.observe(attempt_id)

    def patch(self, attempt_id, base):
        """Call after confirmed termination; include added files and binary edits."""
        path = self._path(attempt_id)
        subprocess.run(
            ["git", "-C", str(path), "add", "--all"], check=True, capture_output=True
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
        ).decode()

    async def wait(self, attempt_id):
        await self.watchers[attempt_id]
        return await self.observe(attempt_id)


async def run_attempt(
    store, adapter, attempt, base, command, env=None, input_text=None
):
    """Trusted local adapter supervisor. Partial work survives failures and timeout."""
    aid = attempt["id"]
    try:
        handle = await adapter.launch(
            aid,
            base,
            command,
            max(0.001, attempt["deadline"] - time.time()),
            env=env,
            input_text=input_text,
        )
    except Exception:
        # A launch error may occur after process creation; require observation.
        state = await adapter.observe(aid)
        store.observe(aid, state["state"], state["termination_confirmed"])
        raise
    try:
        store.observe(aid, "running")
    except sqlite3.Error:
        # Losing the coordinator does not abandon an already approved bounded
        # action. Its adapter watcher still enforces the original deadline.
        pass
    result = await adapter.wait(aid)
    store.observe(aid, result["state"], result["termination_confirmed"])
    patch = adapter.patch(aid, handle["base"])
    artifact = store.save_work(aid, attempt["worker"], patch)
    candidate = store.candidate(aid, attempt["worker"], handle["base"], artifact)
    if result["returncode"]:
        store.problem(
            aid,
            attempt["worker"],
            f"execution {result['state']}; exit {result['returncode']}",
        )
    return {"execution": result, "candidate": candidate}
