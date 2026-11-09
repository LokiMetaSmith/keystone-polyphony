"""Tests verifying architectural unification of the durable collaboration protocol."""

import os
import sys
import tempfile
import pytest

from src.core.collaboration import (
    Coordinator,
    Conflict,
    managed_task,
    select_task,
    CollaborationCoordinator,
    FencedLedger,
    GitWorktreeAdapter,
    TaskObjective,
    ResourceEnvelope,
)
import src.liminal_bridge.coordinator as bridge_coordinator


def test_core_collaboration_canonical_exports():
    """Verify that src.core.collaboration provides the canonical authority exports."""
    assert Coordinator is bridge_coordinator.Coordinator
    assert Conflict is bridge_coordinator.Conflict
    assert managed_task is bridge_coordinator.managed_task
    assert select_task is bridge_coordinator.select_task


def test_managed_task_schema_compatibility():
    """Verify that both legacy task_v2_ IDs and schema_version >= 2 tasks are recognized."""
    # Dict with schema_version = 2
    task_v2_obj = TaskObjective(
        task_id="t_custom_id_123",
        title="Custom ID Task",
        description="Testing schema v2",
        baseline_sha="abc1234",
        acceptance_criteria=["crit"],
        schema_version=2,
    )
    assert managed_task(task_v2_obj.to_dict()) is True

    # Dict with task_v2_ prefix
    assert managed_task({"id": "task_v2_abcd1234ef"}) is True

    # Legacy unmanaged task
    assert managed_task({"id": "legacy_task_1", "schema_version": 1}) is False


def test_unified_coordinator_lifecycle():
    """Verify that Coordinator operates seamlessly from the unified authority."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "authority.db")
        coord = Coordinator(db_path)
        
        # Enroll a task
        task = coord.enroll(
            title="Unified Task",
            requirements="Write test",
            checks=["pytest"],
            reviewers=["alice"],
        )
        assert task["id"].startswith("task_v2_")
        assert managed_task(task) is True

        # Snapshot verification
        snap = coord.snapshot()
        assert any(t["id"] == task["id"] for t in snap["task"])
