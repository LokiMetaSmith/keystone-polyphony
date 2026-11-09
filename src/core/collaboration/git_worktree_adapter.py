"""Concrete GitWorktreeAdapter using detached Git worktrees for isolated attempt execution."""

import os
import subprocess
import shutil
import uuid
from typing import Dict, Any, Optional, Tuple
from .adapter import (
    BaseExecutionAdapter,
    AttemptHandle,
    AttemptObservation,
    AttemptLimits,
    IsolationLevel,
)


class GitWorktreeAdapter(BaseExecutionAdapter):
    """
    Executes attempts in isolated Git worktrees (`git worktree add --detach`).
    Enables native content-addressed commit creation, diff extraction, and conflict detection.
    """

    def __init__(
        self, repo_root: Optional[str] = None, worktree_dir: Optional[str] = None
    ):
        self.repo_root = os.path.abspath(repo_root or os.getcwd())
        self.worktree_base = os.path.abspath(
            worktree_dir or os.path.join(self.repo_root, ".polyphony", "worktrees")
        )
        os.makedirs(self.worktree_base, exist_ok=True)
        self.active_worktrees: Dict[str, str] = {}  # handle_id -> path

    def query_capabilities(self) -> Dict[str, Any]:
        return {
            "isolation_level": IsolationLevel.WORKTREE.value,
            "supports_cancellation": True,
            "supports_resource_limiting": True,
            "supports_tree_merge": True,
        }

    def launch(
        self,
        task_id: str,
        attempt_id: str,
        fence_token: int,
        actor_id: str,
        baseline_ref: str,
        limits: Optional[AttemptLimits] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AttemptHandle:
        handle_id = f"wt_{uuid.uuid4().hex[:12]}"
        worktree_path = os.path.join(self.worktree_base, f"{attempt_id}_{handle_id}")
        limits = limits or AttemptLimits()

        # Create detached worktree from baseline_ref
        cmd = [
            "git",
            "-C",
            self.repo_root,
            "worktree",
            "add",
            "--detach",
            worktree_path,
            baseline_ref,
        ]
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to create git worktree: {result.stderr.strip()}"
            )

        self.active_worktrees[handle_id] = worktree_path

        return AttemptHandle(
            handle_id=handle_id,
            task_id=task_id,
            attempt_id=attempt_id,
            fence_token=fence_token,
            actor_id=actor_id,
            baseline_ref=baseline_ref,
            limits=limits,
            metadata={"worktree_path": worktree_path, **(metadata or {})},
        )

    def get_worktree_path(self, handle: AttemptHandle) -> Optional[str]:
        return self.active_worktrees.get(handle.handle_id)

    def run_command(
        self,
        handle: AttemptHandle,
        command: list,
        timeout: Optional[float] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> subprocess.CompletedProcess:
        """Runs a command isolated inside the attempt's worktree with timeout protection."""
        worktree_path = self.get_worktree_path(handle)
        if not worktree_path or not os.path.exists(worktree_path):
            raise RuntimeError("Worktree not found or already cleaned up")

        effective_timeout = timeout or (
            handle.limits.timeout_seconds if handle.limits else 300.0
        )
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        return subprocess.run(
            command,
            cwd=worktree_path,
            env=merged_env,
            timeout=effective_timeout,
            capture_output=True,
            text=True,
        )

    def extract_diff(self, handle: AttemptHandle) -> str:
        """Extracts the git diff against baseline_ref in the isolated worktree."""
        worktree_path = self.get_worktree_path(handle)
        if not worktree_path or not os.path.exists(worktree_path):
            raise RuntimeError("Worktree not found or already cleaned up")

        # First stage any untracked or modified files if needed, or get diff
        cmd = ["git", "-C", worktree_path, "diff", handle.baseline_ref]
        res = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        if res.returncode != 0:
            raise RuntimeError(f"git diff failed: {res.stderr.strip()}")
        return res.stdout

    def create_candidate_commit(
        self, handle: AttemptHandle, commit_message: str = "Candidate commit"
    ) -> str:
        """Stages all changes in the worktree and commits, returning the candidate commit SHA."""
        worktree_path = self.get_worktree_path(handle)
        if not worktree_path:
            raise RuntimeError("Worktree not found")

        subprocess.run(["git", "-C", worktree_path, "add", "-A"], check=True)
        # Commit changes
        cmd = [
            "git",
            "-C",
            worktree_path,
            "-c",
            "user.name=Polyphony Worker",
            "-c",
            "user.email=worker@polyphony.local",
            "commit",
            "-m",
            commit_message,
        ]
        res = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        if res.returncode != 0 and "nothing to commit" not in res.stdout:
            raise RuntimeError(f"git commit failed: {res.stderr.strip()}")

        rev_cmd = ["git", "-C", worktree_path, "rev-parse", "HEAD"]
        rev_res = subprocess.run(
            rev_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        return rev_res.stdout.strip()

    def detect_merge_conflict(
        self, base_commit: str, branch1_commit: str, branch2_commit: str
    ) -> Tuple[bool, str]:
        """
        Runs git merge-tree --write-tree to detect 3-way integration conflicts cleanly.
        Returns (has_conflict, merge_tree_output_or_conflict_reason).
        """
        cmd = [
            "git",
            "-C",
            self.repo_root,
            "merge-tree",
            "--write-tree",
            base_commit,
            branch1_commit,
            branch2_commit,
        ]
        res = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        if res.returncode == 0:
            return False, res.stdout.strip()
        else:
            return (
                True,
                f"Conflict detected during three-way merge:\n{res.stdout}\n{res.stderr}",
            )

    def observe(self, handle: AttemptHandle) -> AttemptObservation:
        worktree_path = self.get_worktree_path(handle)
        if not worktree_path or not os.path.exists(worktree_path):
            return AttemptObservation(
                handle_id=handle.handle_id,
                status="cleaned_up",
                resource_consumption=0.0,
            )

        diff = self.extract_diff(handle)
        return AttemptObservation(
            handle_id=handle.handle_id,
            status="running",
            resource_consumption=1.0,
            diff_text=diff,
        )

    def cancel(self, handle: AttemptHandle) -> Tuple[bool, float]:
        worktree_path = self.get_worktree_path(handle)
        if worktree_path and os.path.exists(worktree_path):
            # Prune worktree
            subprocess.run(
                [
                    "git",
                    "-C",
                    self.repo_root,
                    "worktree",
                    "remove",
                    "--force",
                    worktree_path,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if os.path.exists(worktree_path):
                shutil.rmtree(worktree_path, ignore_errors=True)
            self.active_worktrees.pop(handle.handle_id, None)
            return True, 1.0

        return True, 0.0

    def cleanup(self) -> None:
        """Removes all managed worktrees."""
        for handle_id, path in list(self.active_worktrees.items()):
            subprocess.run(
                ["git", "-C", self.repo_root, "worktree", "remove", "--force", path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if os.path.exists(path):
                shutil.rmtree(path, ignore_errors=True)
        self.active_worktrees.clear()
