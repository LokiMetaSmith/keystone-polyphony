"""Tests for Slice 3: Self-Organizing Conductor Loop, Advisory Nudges & Legacy Guardrails."""

import pytest
import tempfile
import os
import json
from src.core.collaboration.ledger import FencedLedger
from src.core.collaboration.adapter import DeterministicExecutionAdapter
from src.core.collaboration.coordinator import CollaborationCoordinator
from src.core.collaboration.conductor import EnsembleConductor, WorkerFlowManager
from src.core.collaboration.models import TaskObjective, TaskStatus, ReviewVerdict
from unittest.mock import AsyncMock, patch


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def setup_conductor(temp_db):
    ledger = FencedLedger(db_path=temp_db)
    adapter = DeterministicExecutionAdapter()
    coordinator = CollaborationCoordinator(ledger, adapter)
    conductor = EnsembleConductor(ledger, nudge_cooldown_seconds=10.0)
    return ledger, coordinator, conductor


def test_conductor_nudge_on_contention_and_worker_pivot(setup_conductor):
    """When a worker hits a contested task, Conductor emits a deduplicated nudge suggesting alternative work."""
    ledger, coordinator, conductor = setup_conductor

    # Register 2 tasks: task_A and task_B
    coordinator.register_task(
        task_id="task_A",
        title="Task A",
        description="Desc A",
        baseline_sha="baseA",
        acceptance_criteria=["crit A"],
    )
    coordinator.register_task(
        task_id="task_B",
        title="Task B",
        description="Desc B",
        baseline_sha="baseB",
        acceptance_criteria=["crit B"],
    )

    # Worker 1 acquires task_A
    ok1, h1, _ = coordinator.dispatch_attempt("task_A", "worker_1", now=100.0)
    assert ok1 is True

    # Worker 2 attempts task_A -> 409 Contested
    ok2, h2, reason2 = coordinator.dispatch_attempt("task_A", "worker_2", now=105.0)
    assert ok2 is False
    assert "Contested baton" in reason2

    # Worker 2 flow manager pivots
    flow_mgr = WorkerFlowManager("worker_2", conductor)
    pivot_target = flow_mgr.handle_contention("task_A", now=105.0)

    # Conductor nudged worker_2 to task_B
    assert pivot_target == "task_B"

    # Worker 2 now successfully claims task_B
    ok_pivot, h_pivot, _ = coordinator.dispatch_attempt(
        pivot_target, "worker_2", now=106.0
    )
    assert ok_pivot is True
    assert h_pivot.task_id == "task_B"

    # Cooldown test: Immediate repeated contention within 10s does not spam nudges
    nudge_spam = conductor.observe_contention_and_nudge("task_A", "worker_2", now=110.0)
    assert nudge_spam is None


@pytest.mark.asyncio
async def test_legacy_complete_task_guardrail_for_enrolled_tasks(temp_db, monkeypatch):
    """Legacy complete_task tool rejects unverified completion of enrolled tasks."""
    # Point LIMINAL_COLLAB_DB to temp_db
    monkeypatch.setenv("LIMINAL_COLLAB_DB", temp_db)

    # Import server
    from src.liminal_bridge import server

    ledger = FencedLedger(temp_db)
    coordinator = CollaborationCoordinator(ledger, server.collab_adapter)
    monkeypatch.setattr(server, "collab_ledger", ledger)
    monkeypatch.setattr(server, "collab_coordinator", coordinator)

    # Register enrolled task (schema_version = 2)
    server.collab_coordinator.register_task(
        task_id="task_enrolled_99",
        title="Enrolled Task",
        description="Must have accepted review",
        baseline_sha="base99",
        acceptance_criteria=["crit"],
    )

    # Mesh mock for complete_task
    mock_mesh = AsyncMock()
    mock_mesh.running = True
    mock_mesh.release_baton = AsyncMock()
    mock_mesh.get_kv = lambda k: []
    mock_mesh.update_set = AsyncMock()
    mock_mesh.log_audit_event = AsyncMock()
    server.mesh = mock_mesh

    # Attempt to complete without accepted candidate receipt
    with patch.object(server, "ensure_mesh"), patch.object(
        server, "check_warmup", return_value=None
    ):
        msg = await server.complete_task("task_enrolled_99")
        assert "DENIED" in msg
        assert "Collaboration Protocol" in msg

    # Now simulate valid contribution and passing review
    ok_disp, h, _ = server.collab_coordinator.dispatch_attempt(
        "task_enrolled_99", "worker_alice", now=100.0
    )
    ok_sub, sub, _ = server.collab_coordinator.submit_attempt(
        "task_enrolled_99",
        h.attempt_id,
        "worker_alice",
        1,
        "req99",
        "diff",
        2.0,
        now=110.0,
    )
    ok_rev, _, _ = server.collab_coordinator.record_review(
        sub.candidate_sha,
        "task_enrolled_99",
        "reviewer_bob",
        ReviewVerdict.PASS,
        0,
        now=120.0,
    )
    assert ok_rev is True

    with patch.object(server, "ensure_mesh"), patch.object(
        server, "check_warmup", return_value=None
    ):
        msg_ok = await server.complete_task("task_enrolled_99")
        assert "completed" in msg_ok
