"""An admin-pinned installation never weakens ordinary workflow provenance."""

import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest

spec = importlib.util.spec_from_file_location(
    "bootstrap_gate", Path(__file__).parents[1] / "scripts/decision-merge.py"
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
PIN = "d" * 40
BASE = "8f23c9c7b721ad47ffbf5358a812dac2dba66999"
REPO = "niklas-olsson/keystone-polyphony"


@pytest.fixture
def installation(monkeypatch):
    environment = {
        "DECISION_GATE_BOOTSTRAP_SHA": PIN,
        "GITHUB_SHA": PIN,
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_ACTOR": "niklas-olsson",
        "GITHUB_REF": "refs/heads/feat/lokimetasmith-sync",
        "GITHUB_REPOSITORY": REPO,
    }
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    github = Mock(repository=REPO)
    github.api.side_effect = [{"sha": "old-workflow"}, {"sha": "new-workflow"}]
    pr = {
        "number": 86,
        "head": {
            "sha": PIN,
            "ref": "feat/lokimetasmith-sync",
            "repo": {"full_name": REPO},
        },
        "base": {"sha": BASE},
    }
    run = {
        "head_sha": PIN,
        "event": "pull_request",
        "actor": {"login": "niklas-olsson"},
    }
    evidence = {"workflow_path": ".github/workflows/opencode.yml"}
    return github, run, evidence, pr, environment


def test_owner_pinned_exact_installation_is_accepted(installation):
    github, run, evidence, pr, _ = installation
    gate.verify_workflow(github, run, evidence, pr)


@pytest.mark.parametrize(
    "key",
    [
        "DECISION_GATE_BOOTSTRAP_SHA",
        "GITHUB_SHA",
        "GITHUB_EVENT_NAME",
        "GITHUB_ACTOR",
        "GITHUB_REF",
        "GITHUB_REPOSITORY",
    ],
)
def test_every_execution_trust_anchor_is_required(installation, monkeypatch, key):
    github, run, evidence, pr, _ = installation
    monkeypatch.setenv(key, "untrusted")
    with pytest.raises(gate.Hold):
        gate.verify_workflow(github, run, evidence, pr)


@pytest.mark.parametrize(
    "mutation", ["number", "head", "base", "run", "actor", "workflow"]
)
def test_pin_does_not_authorize_other_prs_or_evidence(installation, mutation):
    github, run, evidence, pr, _ = installation
    if mutation == "number":
        pr["number"] = 87
    elif mutation == "head":
        pr["head"]["sha"] = "f" * 40
    elif mutation == "base":
        pr["base"]["sha"] = "f" * 40
    elif mutation == "run":
        run["head_sha"] = "f" * 40
    elif mutation == "actor":
        run["actor"]["login"] = "other"
    else:
        evidence["workflow_path"] = ".github/workflows/workflow-review-dispatch.yml"
    with pytest.raises(gate.Hold):
        gate.verify_workflow(github, run, evidence, pr)


def test_trusted_target_event_can_review_changed_pr_workflow(installation):
    github, run, evidence, pr, _ = installation
    pr["base"].update(ref="main", repo={"id": 123})
    run.update(
        event="pull_request_target",
        pull_requests=[
            {"number": 86, "base": {"sha": BASE, "ref": "main", "repo": {"id": 123}}}
        ],
    )
    gate.verify_workflow(github, run, evidence, pr)
    assert github.api.call_count == 1


@pytest.mark.parametrize("mutation", ["number", "sha", "repo", "ref"])
def test_target_event_must_bind_to_same_pr_base(installation, mutation):
    github, run, evidence, pr, _ = installation
    pr["base"].update(ref="main", repo={"id": 123})
    target = {"number": 86, "base": {"sha": BASE, "ref": "main", "repo": {"id": 123}}}
    run.update(event="pull_request_target", pull_requests=[target])
    if mutation == "number":
        target["number"] = 87
    elif mutation == "sha":
        target["base"]["sha"] = "e" * 40
    elif mutation == "repo":
        target["base"]["repo"]["id"] = 456
    else:
        target["base"]["ref"] = "staging"
    with pytest.raises(gate.Hold, match="not bound"):
        gate.verify_workflow(github, run, evidence, pr)
