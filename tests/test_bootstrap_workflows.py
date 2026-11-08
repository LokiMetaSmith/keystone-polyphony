"""Exercise the one-time installation guards without contacting GitHub."""

import json
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).parents[1]
SHA = "a" * 40
BASE = "8f23c9c7b721ad47ffbf5358a812dac2dba66999"
REPO = "niklas-olsson/keystone-polyphony"


def run_step(tmp_path, name, payload, **env):
    text = (ROOT / ".github/workflows/decision-merge.yml").read_text()
    step = text.split(f"      - name: {name}\n", 1)[1]
    block = step.split("        run: |\n", 1)[1]
    lines = []
    for line in block.splitlines():
        if line and not line.startswith("          "):
            break
        lines.append(line[10:])
    fake_gh = tmp_path / "gh"
    fake_gh.write_text('#!/bin/sh\ncat "$FAKE_RESPONSE"\n')
    fake_gh.chmod(0o755)
    response = tmp_path / "response.json"
    response.write_text(json.dumps(payload))
    outputs = tmp_path / "outputs"
    result = subprocess.run(
        ["bash", "-c", "\n".join(lines)],
        cwd=tmp_path,
        env=dict(
            os.environ,
            PATH=str(tmp_path) + os.pathsep + os.environ["PATH"],
            FAKE_RESPONSE=str(response),
            GITHUB_OUTPUT=str(outputs),
            REPO=REPO,
            BOOTSTRAP_SHA=SHA,
            EVENT_SHA=SHA,
            **env,
        ),
        capture_output=True,
        text=True,
    )
    return result, outputs.read_text() if outputs.exists() else ""


def candidate():
    return {
        "state": "open",
        "draft": False,
        "head": {
            "sha": SHA,
            "repo": {"full_name": REPO},
            "ref": "feat/lokimetasmith-sync",
        },
        "base": {"ref": "main", "sha": BASE},
        "labels": [{"name": "decision-merge"}],
    }


def test_installation_candidate_guard_accepts_only_pinned_candidate(tmp_path):
    result, _ = run_step(
        tmp_path, "Verify owner-pinned installation candidate", candidate()
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "mutation", ["sha", "repo", "branch", "base", "label", "draft"]
)
def test_installation_candidate_guard_rejects_changed_candidate(tmp_path, mutation):
    pr = candidate()
    if mutation == "sha":
        pr["head"]["sha"] = "b" * 40
    elif mutation == "repo":
        pr["head"]["repo"]["full_name"] = "other/fork"
    elif mutation == "branch":
        pr["head"]["ref"] = "other"
    elif mutation == "base":
        pr["base"]["sha"] = "b" * 40
    elif mutation == "label":
        pr["labels"] = []
    else:
        pr["draft"] = True
    result, _ = run_step(tmp_path, "Verify owner-pinned installation candidate", pr)
    assert result.returncode != 0


@pytest.mark.parametrize("conclusion,expected", [("success", 0), ("failure", 1)])
def test_installation_wait_requires_completed_success(tmp_path, conclusion, expected):
    result, outputs = run_step(
        tmp_path,
        "Wait for independent installation review",
        {"id": 123, "status": "completed", "conclusion": conclusion},
    )
    assert result.returncode == expected
    assert ("run_id=123" in outputs) == (expected == 0)


def test_installation_wait_does_not_hold_staging_writer_lock():
    text = (ROOT / ".github/workflows/decision-merge.yml").read_text()
    before_gate, gate = text.split("  decision-gate:\n", 1)
    assert "concurrency:" not in before_gate
    assert "needs: installation-review" in gate
    assert "needs.installation-review.result == 'success'" in gate
    assert "group: auto-merge-staging" in gate
    assert "needs.installation-review.outputs.run_id" in gate


def test_normal_reviews_use_trusted_target_workflow_and_bootstrap_is_pinned():
    text = (ROOT / ".github/workflows/opencode.yml").read_text()
    condition = text.split("    if: |\n", 1)[1].split("    runs-on:", 1)[0]
    pr_gate = condition.split("((github.event_name == 'pull_request' &&", 1)[1]
    bootstrap, normal_target = pr_gate.split(" ||\n", 1)
    assert "github.event.pull_request.number == 86" in bootstrap
    assert "vars.DECISION_GATE_BOOTSTRAP_SHA != ''" in bootstrap
    assert "head.sha == vars.DECISION_GATE_BOOTSTRAP_SHA" in bootstrap
    assert "head.repo.full_name == github.repository" in bootstrap
    assert "head.ref == 'feat/lokimetasmith-sync'" in bootstrap
    assert f"base.sha == '{BASE}'" in bootstrap
    assert normal_target.startswith(
        "         github.event_name == 'pull_request_target') &&"
    )
    assert "head.repo.full_name != github.repository" not in condition
