"""Tests for automated conductor contention tracking and dynamic task decomposition."""

import pytest
import tempfile
import os
from src.core.collaboration.ledger import FencedLedger
from src.core.collaboration.conductor import EnsembleConductor
from src.core.collaboration.models import TaskObjective, TaskStatus


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_contention_tracking_and_task_decomposition(temp_db):
    ledger = FencedLedger(temp_db)
    conductor = EnsembleConductor(ledger, nudge_cooldown_seconds=0.0)

    # Create root task
    task = TaskObjective(
        task_id="t_heavy_core",
        title="Heavy Core Refactor",
        description="Refactor critical subsystem",
        baseline_sha="base_refactor",
        acceptance_criteria=["crit1"],
    )
    ledger.create_task(task)

    # 1st contention
    conductor.observe_contention_and_nudge("t_heavy_core", "worker_1", now=10.0)
    assert conductor.contention_counts["t_heavy_core"] == 1
    assert "t_heavy_core" not in conductor.decomposition_proposals

    # 2nd contention -> triggers dynamic decomposition proposal
    n2 = conductor.observe_contention_and_nudge("t_heavy_core", "worker_2", now=12.0)
    assert conductor.contention_counts["t_heavy_core"] == 2
    assert "t_heavy_core" in conductor.decomposition_proposals
    assert "Proposed decomposition" in n2.suggested_action

    prop = conductor.decomposition_proposals["t_heavy_core"]
    assert "t_heavy_core_protocol" in prop["subtask_ids"]

    # Apply decomposition
    subtasks = conductor.apply_decomposition("t_heavy_core")
    assert len(subtasks) == 3
    assert {st.task_id for st in subtasks} == set(prop["subtask_ids"])

    # Original task should now be HELD
    orig_after = ledger.get_task("t_heavy_core")
    assert orig_after.status == TaskStatus.HELD
