import os
from pathlib import Path
import subprocess
import sys
import asyncio
import importlib.util

import pytest

ROOT = Path(__file__).resolve().parents[1]
DISPATCH = ROOT / "scripts" / "triage-dispatch.sh"


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
    )


@pytest.mark.parametrize("agents", ["", " , , "])
def test_no_configured_agents_holds_issue(tmp_path, agents):
    issue = tmp_path / "issue.md"
    issue.write_text("# Raw issue\n")
    result = dispatch(issue, TRIAGE_AGENTS=agents)
    assert result.returncode == 0
    assert result.stdout.strip() == "NO_AGENTS_CONFIGURED"
    assert issue.read_text() == "# Raw issue\n"


def test_cli_agent_refines_once_and_failure_is_not_marked(tmp_path):
    issue = tmp_path / "issue.md"
    issue.write_text("# Raw issue\n")
    agent = tmp_path / "agent"
    agent.write_text(
        "#!/bin/sh\nprintf 'Agent progress\\n'\nprintf 'Refined\\n' >> \"$1\"\n"
    )
    agent.chmod(0o755)
    variables = {"TRIAGE_AGENTS": "example", "EXAMPLE_COMMAND": str(agent)}

    result = dispatch(issue, **variables)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ALL_REFINED"
    assert "Agent progress" in result.stderr
    assert issue.read_text().count("Refined\n") == 1
    assert "<!-- triage-refined: example -->" in issue.read_text()
    result = dispatch(issue, **variables)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ALL_REFINED"
    assert issue.read_text().count("Refined\n") == 1

    failed = tmp_path / "failed.md"
    failed.write_text("# Raw issue\n")
    agent.write_text("#!/bin/sh\nexit 1\n")
    result = dispatch(failed, **variables)
    assert result.returncode != 0
    assert "triage-refined" not in failed.read_text()


def test_unconfigured_architect_cannot_claim_refinement(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "refine_issue", ROOT / "scripts" / "refine_issue.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module,
        "Architect",
        lambda: type("Unconfigured", (), {"client": None, "google_model": None})(),
    )
    issue = tmp_path / "issue.md"
    issue.write_text("# Raw issue\n")
    monkeypatch.setattr(sys, "argv", ["refine_issue.py", str(issue)])

    with pytest.raises(SystemExit) as exc:
        asyncio.run(module.main())
    assert exc.value.code != 0
    assert issue.read_text() == "# Raw issue\n"
