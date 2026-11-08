#!/usr/bin/env python3
"""Publish bounded review evidence for an unchanged PR, using trusted-base code."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from liminal_bridge.review_result import review_passed

MAX_REVIEW_BYTES = 60000
SHA = re.compile(r"[0-9a-f]{40}")


def build_evidence(
    snapshot,
    current,
    review_bytes,
    *,
    repository,
    run_id,
    run_attempt,
    workflow_path,
    model,
    scope,
    exit_code,
):
    """Validate identity and immutable revisions before producing inert JSON data."""
    if exit_code != 0:
        raise ValueError("review CLI failed")
    if scope not in {"general", "workflow"}:
        raise ValueError("unsupported review scope")
    if workflow_path not in {
        ".github/workflows/opencode.yml",
        ".github/workflows/workflow-review-dispatch.yml",
    }:
        raise ValueError("unsupported review workflow")
    if not repository or not model.strip() or run_id < 1 or run_attempt < 1:
        raise ValueError("missing review run identity")
    if type(snapshot.get("number")) is not int or snapshot["number"] < 1:
        raise ValueError("invalid PR number")
    for pr in (snapshot, current):
        if pr.get("state") != "open" or pr.get("merged"):
            raise ValueError("PR is no longer open")
        if pr.get("base", {}).get("repo", {}).get("full_name") != repository:
            raise ValueError("PR repository mismatch")
        for side in ("head", "base"):
            if not SHA.fullmatch(pr.get(side, {}).get("sha", "")):
                raise ValueError("invalid PR revision")
    if snapshot["number"] != current.get("number") or any(
        snapshot[side]["sha"] != current[side]["sha"] for side in ("head", "base")
    ):
        raise ValueError("PR revisions changed during review")
    if not review_bytes or len(review_bytes) > MAX_REVIEW_BYTES:
        raise ValueError("empty or oversized review")
    review_text = review_bytes.decode("utf-8", errors="strict").strip()
    if not review_text or any(
        ord(char) < 32 and char not in "\n\t" for char in review_text
    ):
        raise ValueError("empty or malformed review text")
    # Error placeholders and bootstrap-only output must never become review evidence.
    if not re.search(r"^#{1,6}\s+", review_text, flags=re.MULTILINE):
        raise ValueError("review must contain Markdown analysis sections")
    if not review_passed(review_bytes.decode("utf-8", errors="strict")):
        raise ValueError(
            "automatic review must explicitly PASS with no blocking findings"
        )
    return {
        "version": 2,
        "repository": repository,
        "pr_number": snapshot["number"],
        "head_sha": snapshot["head"]["sha"],
        "base_sha": snapshot["base"]["sha"],
        "run_id": run_id,
        "run_attempt": run_attempt,
        "workflow_path": workflow_path,
        "model": model,
        "review_text": review_text,
        "exit_code": 0,
        "scope": scope,
        "review_verdict": "PASS",
        "blocking_findings": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("snapshot", "review", "output", "scope", "model", "workflow-path"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--exit-code", required=True, type=int)
    args = parser.parse_args()
    output = Path(args.output)
    output.unlink(missing_ok=True)
    repository = os.environ["GITHUB_REPOSITORY"]
    snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    number = snapshot.get("number")
    if type(number) is not int or number < 1:
        raise ValueError("invalid PR number")
    response = subprocess.run(
        ["gh", "api", f"/repos/{repository}/pulls/{number}"],
        check=True,
        capture_output=True,
        text=True,
    )
    evidence = build_evidence(
        snapshot,
        json.loads(response.stdout),
        Path(args.review).read_bytes(),
        repository=repository,
        run_id=int(os.environ["GITHUB_RUN_ID"]),
        run_attempt=int(os.environ["GITHUB_RUN_ATTEMPT"]),
        workflow_path=args.workflow_path,
        model=args.model,
        scope=args.scope,
        exit_code=args.exit_code,
    )
    output.write_text(json.dumps(evidence, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
