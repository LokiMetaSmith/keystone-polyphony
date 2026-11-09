"""Repository admission handoff producing schema-v2 review-evidence.json matching docs/decision-merge.md."""

from typing import Dict, Any, Optional
import json
import hashlib
import time
from .models import TaskObjective, CandidateReceipt, ReviewReceipt, ReviewVerdict
from .ledger import FencedLedger


class AdmissionHandoffEmitter:
    """
    Generates structured review evidence and admission packets from accepted candidate
    records in the collaboration ledger, ensuring strict alignment with docs/decision-merge.md.
    """

    def __init__(
        self, ledger: FencedLedger, repository: str = "niklas-olsson/keystone-polyphony"
    ):
        self.ledger = ledger
        self.repository = repository

    def emit_review_evidence(
        self,
        task_id: str,
        workflow_path: str = ".github/workflows/opencode.yml",
        run_id: int = 12345678,
        run_attempt: int = 1,
        pr_number: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Emits schema-v2 review-evidence.json bound to repository, head/base SHAs,
        workflow path, run ID, and run attempt with an explicit PASS verdict and 0 blocking findings.
        """
        task = self.ledger.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        if not task.accepted_candidate_id:
            raise ValueError(f"Task {task_id} has no accepted candidate")

        candidate = self.ledger.get_candidate(task.accepted_candidate_id)
        if not candidate:
            raise ValueError(f"Candidate {task.accepted_candidate_id} not found")

        valid_reviews = self.ledger.get_valid_reviews_for_candidate(
            candidate.candidate_id
        )
        passing_reviews = [
            r
            for r in valid_reviews
            if r.verdict == ReviewVerdict.PASS and r.blocking_findings == 0
        ]
        if not passing_reviews:
            raise ValueError(
                f"No passing review with 0 blocking findings for candidate {candidate.candidate_id}"
            )

        selected_review = passing_reviews[0]

        evidence = {
            "schema_version": 2,
            "repository": self.repository,
            "pr_number": pr_number,
            "head_sha": candidate.candidate_id,
            "base_sha": candidate.baseline_sha,
            "workflow_path": workflow_path,
            "run_id": run_id,
            "run_attempt": run_attempt,
            "verdict": "PASS",
            "blocking_findings": 0,
            "summary": f"Accepted candidate {candidate.candidate_id[:12]} verified by {selected_review.reviewer_actor_id}",
            "reviewer_actor_id": selected_review.reviewer_actor_id,
            "spec_revision": candidate.spec_revision,
            "timestamp": time.time(),
        }
        return evidence

    def write_evidence_file(
        self,
        task_id: str,
        output_path: str = "review-evidence.json",
        workflow_path: str = ".github/workflows/opencode.yml",
        run_id: int = 12345678,
        run_attempt: int = 1,
        pr_number: Optional[int] = None,
    ) -> str:
        """Writes review-evidence.json directly to disk for CI/CD ingestion."""
        evidence = self.emit_review_evidence(
            task_id=task_id,
            workflow_path=workflow_path,
            run_id=run_id,
            run_attempt=run_attempt,
            pr_number=pr_number,
        )
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(evidence, f, indent=2)
        return output_path
