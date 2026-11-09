"""Tests for admission handoff evidence writer."""

import pytest
import tempfile
import os
import json
from src.core.collaboration.ledger import FencedLedger
from src.core.collaboration.coordinator import CollaborationCoordinator
from src.core.collaboration.adapter import DeterministicExecutionAdapter
from src.core.collaboration.admission import AdmissionHandoffEmitter
from src.core.collaboration.models import ReviewVerdict


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_write_evidence_file(temp_db):
    ledger = FencedLedger(temp_db)
    adapter = DeterministicExecutionAdapter()
    coord = CollaborationCoordinator(ledger, adapter)
    admission = AdmissionHandoffEmitter(ledger)

    coord.register_task(
        task_id="t_evidence_1",
        title="Evidence Task",
        description="Desc",
        baseline_sha="base_ev_1",
        acceptance_criteria=["crit"],
    )

    ok1, h1, _ = coord.dispatch_attempt("t_evidence_1", "dev_1", now=10.0)
    ok_sub, sub, _ = coord.submit_attempt(
        "t_evidence_1", h1.attempt_id, "dev_1", 1, "req1", "diff", 2.0, now=20.0
    )
    coord.record_review(
        sub.candidate_sha, "t_evidence_1", "rev_1", ReviewVerdict.PASS, 0, now=30.0
    )

    fd_out, out_path = tempfile.mkstemp(suffix=".json")
    os.close(fd_out)

    try:
        admission.write_evidence_file(
            "t_evidence_1", output_path=out_path, pr_number=101
        )
        with open(out_path, "r") as f:
            data = json.load(f)
        assert data["schema_version"] == 2
        assert data["verdict"] == "PASS"
        assert data["pr_number"] == 101
        assert data["head_sha"] == sub.candidate_sha
    finally:
        if os.path.exists(out_path):
            os.remove(out_path)
