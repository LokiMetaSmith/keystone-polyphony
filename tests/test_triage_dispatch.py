"""Adversarial checks for fail-closed issue refinement."""

import asyncio
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
DISPATCH = ROOT / "scripts" / "triage-dispatch.sh"
VALIDATE = ROOT / "scripts" / "validate_issue.py"
VALID = """# Feature: Shared review contract

## Human Interaction Story
As an agent, I can hand work to another reviewer.

## Prerequisites
- An approved task authority

## Scope
- Provide a review receipt

## Acceptance Criteria
- [ ] Record an immutable reviewer result

## BDD Feature
~~~gherkin
Feature: Independent review
  Scenario: The reviewer checks the artifact
    Given an immutable candidate exists
    When an independent reviewer evaluates it
    Then the result is recorded
~~~
"""


def dispatch(issue, **variables):
    env = os.environ.copy()
    env.update({"TRIAGE_AGENTS": "", "VARS_JSON": "", "AGENT_DAILY_TASKS": "0"})
    env.update(variables)
    return subprocess.run(
        ["bash", str(DISPATCH), str(issue), "owner/repo"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.parametrize("agents", ["", " , , "])
def test_no_agents_hold_issue(tmp_path, agents):
    issue = tmp_path / "issue.md"
    issue.write_text("# Raw issue\n")
    result = dispatch(issue, TRIAGE_AGENTS=agents)
    assert result.returncode == 0
    assert result.stdout.strip() == "NO_AGENTS_CONFIGURED"
    assert issue.read_text() == "# Raw issue\n"


def test_successful_refinement_is_idempotent_and_separates_output(tmp_path):
    issue = tmp_path / "issue.md"
    issue.write_text("# Raw issue\n")
    agent = tmp_path / "reviewer"
    agent.write_text(
        "#!/bin/sh\ncat \"$TRIAGE_TEST_BODY\" > \"$1\"\nprintf 'agent logs\\n'\n"
    )
    agent.chmod(0o755)
    payload = tmp_path / "body.md"
    payload.write_text(VALID)
    variables = {
        "TRIAGE_AGENTS": "example",
        "EXAMPLE_COMMAND": str(agent),
        "TRIAGE_TEST_BODY": str(payload),
    }
    result = dispatch(issue, **variables)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ALL_REFINED"
    assert "agent logs" in result.stderr
    assert "agent logs" not in result.stdout
    assert "<!-- triage-refined: example -->" in issue.read_text()
    before = issue.read_text()
    result = dispatch(issue, **variables)
    assert result.stdout.strip() == "ALL_REFINED"
    assert issue.read_text() == before


@pytest.mark.parametrize(
    "script,expected",
    [
        ("#!/bin/sh\nexit 1\n", "Error: CLI agent"),
        ("#!/bin/sh\nexit 0\n", "NO_REFINEMENT"),
    ],
)
def test_failed_or_noop_agent_cannot_claim_refinement(tmp_path, script, expected):
    issue = tmp_path / "issue.md"
    issue.write_text("# Raw issue\n")
    agent = tmp_path / "reviewer"
    agent.write_text(script)
    agent.chmod(0o755)
    result = dispatch(issue, TRIAGE_AGENTS="example", EXAMPLE_COMMAND=str(agent))
    assert expected in (result.stderr + result.stdout)
    assert "triage-refined" not in issue.read_text()
    assert issue.read_text() == "# Raw issue\n"


def test_forged_marker_cannot_publish_incomplete_issue(tmp_path):
    issue = tmp_path / "issue.md"
    issue.write_text("# Raw issue\n<!-- triage-refined: example -->\n")
    result = dispatch(issue, TRIAGE_AGENTS="example")
    assert result.returncode == 0
    assert result.stdout.strip() == "INVALID_REFINEMENT"
    assert "ALL_REFINED" not in result.stdout


@pytest.mark.parametrize(
    "invalid",
    [
        "# Raw issue\n",
        VALID.replace("Scenario: The reviewer checks the artifact", "Example: missing"),
        VALID.replace("## Prerequisites", "## Nothing"),
        VALID.replace("## Scope", "## Nothing"),
        VALID.replace("## Acceptance Criteria", "## Nothing"),
    ],
)
def test_validator_rejects_incomplete_structures(tmp_path, invalid):
    issue = tmp_path / "issue.md"
    issue.write_text(invalid)
    result = subprocess.run(
        [sys.executable, str(VALIDATE), str(issue)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "not publishable" in result.stderr


def test_validator_accepts_complete_issue(tmp_path):
    issue = tmp_path / "issue.md"
    issue.write_text(VALID)
    result = subprocess.run(
        [sys.executable, str(VALIDATE), str(issue)],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0


def test_unconfigured_architect_must_fail(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "refine_issue", ROOT / "scripts" / "refine_issue.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module,
        "Architect",
        lambda: type("Unconfigured", (), {"is_configured": lambda self: False})(),
    )
    issue = tmp_path / "issue.md"
    issue.write_text("# Raw issue\n")
    monkeypatch.setattr(sys, "argv", ["refine_issue.py", str(issue)])
    with pytest.raises(SystemExit) as exc:
        asyncio.run(module.main())
    assert exc.value.code != 0
    assert issue.read_text() == "# Raw issue\n"


def test_unsafe_agent_identifier_fails_closed(tmp_path):
    issue = tmp_path / "issue.md"
    issue.write_text("# Raw issue\n")
    result = dispatch(issue, TRIAGE_AGENTS="not_safe$(id)")
    assert result.stdout.strip() == "INVALID_AGENT"
    assert issue.read_text() == "# Raw issue\n"
