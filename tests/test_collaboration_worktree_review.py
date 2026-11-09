"""Tests for Slice 2: Concrete GitWorktreeAdapter, Multi-Worker Collaboration & Review."""

import pytest
import tempfile
import os
import subprocess
from src.core.collaboration.ledger import FencedLedger
from src.core.collaboration.git_worktree_adapter import GitWorktreeAdapter
from src.core.collaboration.coordinator import CollaborationCoordinator
from src.core.collaboration.models import (
    ReviewVerdict,
    TaskStatus,
)


@pytest.fixture
def test_git_repo():
    """Initializes a real temporary git repository with initial commit."""
    temp_dir = tempfile.mkdtemp(prefix="polyphony_test_repo_")
    subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=temp_dir,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test Committer"], cwd=temp_dir, check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@polyphony.local"],
        cwd=temp_dir,
        check=True,
    )

    test_file = os.path.join(temp_dir, "hello.txt")
    with open(test_file, "w") as f:
        f.write("initial baseline content\n")
    subprocess.run(["git", "add", "hello.txt"], cwd=temp_dir, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=temp_dir,
        check=True,
        stdout=subprocess.DEVNULL,
    )

    rev_proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=temp_dir,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    baseline_sha = rev_proc.stdout.strip()

    yield temp_dir, baseline_sha

    # Cleanup
    import shutil

    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def worktree_coordinator(test_git_repo):
    repo_dir, baseline_sha = test_git_repo
    db_path = os.path.join(repo_dir, "collaboration.db")
    ledger = FencedLedger(db_path=db_path)
    adapter = GitWorktreeAdapter(repo_root=repo_dir)
    coordinator = CollaborationCoordinator(ledger=ledger, execution_adapter=adapter)
    return coordinator, ledger, adapter, baseline_sha, repo_dir


def test_git_worktree_adapter_isolation_and_diff(worktree_coordinator):
    """Verify that GitWorktreeAdapter launches in isolated worktree and extracts diff."""
    coordinator, ledger, adapter, baseline_sha, repo_dir = worktree_coordinator

    coordinator.register_task(
        task_id="task_wt_1",
        title="Worktree Task",
        description="Isolated task",
        baseline_sha=baseline_sha,
        acceptance_criteria=["Modify hello.txt"],
    )

    ok, handle, _ = coordinator.dispatch_attempt(
        task_id="task_wt_1",
        actor_id="worker_isolated_1",
        now=100.0,
    )
    assert ok is True
    wt_path = adapter.get_worktree_path(handle)
    assert wt_path is not None
    assert os.path.isdir(wt_path)

    # Modify file in worktree
    wt_file = os.path.join(wt_path, "hello.txt")
    with open(wt_file, "a") as f:
        f.write("added worker modification\n")

    # Extract diff
    diff = adapter.extract_diff(handle)
    assert "+added worker modification" in diff

    # Create candidate commit in worktree
    commit_sha = adapter.create_candidate_commit(handle, "Worker 1 modification")
    assert commit_sha != baseline_sha

    # Submit contribution
    ok_sub, sub, _ = coordinator.submit_attempt(
        task_id="task_wt_1",
        assignment_id=handle.attempt_id,
        actor_id="worker_isolated_1",
        fence_token=handle.fence_token,
        request_id="req_wt_1",
        diff_text=diff,
        actual_cost=2.0,
        now=110.0,
    )
    assert ok_sub is True
    assert sub.candidate_sha is not None

    # Clean up worktree
    ok_cancel, cost = adapter.cancel(handle)
    assert ok_cancel is True
    assert not os.path.exists(wt_path)


def test_three_way_merge_tree_conflict_detection(worktree_coordinator):
    """Verify that git merge-tree detects conflicts cleanly."""
    coordinator, ledger, adapter, baseline_sha, repo_dir = worktree_coordinator

    # Branch 1
    subprocess.run(
        ["git", "checkout", "-b", "branch1", baseline_sha],
        cwd=repo_dir,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    with open(os.path.join(repo_dir, "hello.txt"), "w") as f:
        f.write("conflict version A\n")
    subprocess.run(
        ["git", "commit", "-am", "Branch 1 change"],
        cwd=repo_dir,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    b1_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_dir,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.strip()

    # Branch 2 from baseline
    subprocess.run(
        ["git", "checkout", "-b", "branch2", baseline_sha],
        cwd=repo_dir,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    with open(os.path.join(repo_dir, "hello.txt"), "w") as f:
        f.write("conflict version B\n")
    subprocess.run(
        ["git", "commit", "-am", "Branch 2 change"],
        cwd=repo_dir,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    b2_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_dir,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.strip()

    # Detect conflict
    has_conflict, output = adapter.detect_merge_conflict(baseline_sha, b1_sha, b2_sha)
    assert has_conflict is True
    assert "Conflict detected" in output


def test_reviewer_independence_author_cannot_review(worktree_coordinator):
    """Enforce author_actor_id != reviewer_actor_id at the coordinator level."""
    coordinator, ledger, adapter, baseline_sha, repo_dir = worktree_coordinator

    coordinator.register_task(
        task_id="task_rev_1",
        title="Review Independence Task",
        description="Verify author cannot review",
        baseline_sha=baseline_sha,
        acceptance_criteria=["crit"],
    )

    ok, handle, _ = coordinator.dispatch_attempt(
        task_id="task_rev_1",
        actor_id="author_alice",
        now=100.0,
    )
    ok_sub, sub, _ = coordinator.submit_attempt(
        task_id="task_rev_1",
        assignment_id=handle.attempt_id,
        actor_id="author_alice",
        fence_token=1,
        request_id="req_rev_1",
        diff_text="diff by alice",
        actual_cost=3.0,
        now=110.0,
    )
    candidate_id = sub.candidate_sha

    # Alice attempts to review her own candidate -> REJECTED
    ok_rev_self, rec_self, msg_self = coordinator.record_review(
        candidate_id=candidate_id,
        task_id="task_rev_1",
        reviewer_actor_id="author_alice",
        verdict=ReviewVerdict.PASS,
        blocking_findings=0,
        now=120.0,
    )
    assert ok_rev_self is False
    assert rec_self is None
    assert "Reviewer independence violation" in msg_self

    # Independent reviewer Bob reviews candidate -> ACCEPTED
    ok_rev_bob, rec_bob, msg_bob = coordinator.record_review(
        candidate_id=candidate_id,
        task_id="task_rev_1",
        reviewer_actor_id="reviewer_bob",
        verdict=ReviewVerdict.PASS,
        blocking_findings=0,
        notes="Clean review",
        now=125.0,
    )
    assert ok_rev_bob is True
    assert rec_bob is not None
    assert rec_bob.verdict == ReviewVerdict.PASS

    task = ledger.get_task("task_rev_1")
    assert task.status == TaskStatus.ACCEPTED
    assert task.accepted_candidate_id == candidate_id


def test_spec_revision_bump_invalidates_prior_reviews(worktree_coordinator):
    """Any bump to spec_revision or baseline_sha invalidates prior candidate review receipts."""
    coordinator, ledger, adapter, baseline_sha, repo_dir = worktree_coordinator

    coordinator.register_task(
        task_id="task_bump_1",
        title="Bumping Task",
        description="Verify spec bump invalidation",
        baseline_sha=baseline_sha,
        acceptance_criteria=["Initial criteria"],
    )

    ok, handle, _ = coordinator.dispatch_attempt(
        task_id="task_bump_1",
        actor_id="dev_charlie",
        now=100.0,
    )
    ok_sub, sub, _ = coordinator.submit_attempt(
        task_id="task_bump_1",
        assignment_id=handle.attempt_id,
        actor_id="dev_charlie",
        fence_token=1,
        request_id="req_bump_1",
        diff_text="diff by charlie",
        actual_cost=2.0,
        now=110.0,
    )
    candidate_id = sub.candidate_sha

    # Reviewer Dave passes it
    coordinator.record_review(
        candidate_id=candidate_id,
        task_id="task_bump_1",
        reviewer_actor_id="reviewer_dave",
        verdict=ReviewVerdict.PASS,
        blocking_findings=0,
        now=115.0,
    )
    task_before = ledger.get_task("task_bump_1")
    assert task_before.status == TaskStatus.ACCEPTED

    # Requirements change: bump spec revision
    ok_bump, bumped_task, msg_bump = ledger.bump_spec_revision(
        task_id="task_bump_1",
        new_acceptance_criteria=["Updated criteria requiring new changes"],
        now=120.0,
    )
    assert ok_bump is True
    assert bumped_task.spec_revision == 2
    assert bumped_task.status == TaskStatus.HELD
    assert bumped_task.accepted_candidate_id is None

    # Prior reviews for this candidate are now invalid
    valid_reviews = ledger.get_valid_reviews_for_candidate(candidate_id)
    assert len(valid_reviews) == 0

    # Attempting to review stale candidate under new revision is rejected
    ok_stale, _, msg_stale = coordinator.record_review(
        candidate_id=candidate_id,
        task_id="task_bump_1",
        reviewer_actor_id="reviewer_dave",
        verdict=ReviewVerdict.PASS,
        blocking_findings=0,
        now=125.0,
    )
    assert ok_stale is False
    assert "Candidate is stale" in msg_stale
