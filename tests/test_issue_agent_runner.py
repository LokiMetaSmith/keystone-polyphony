"""Exercise the issue runner and workflow wiring without provider or GitHub calls."""

import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).parents[1]
RUNNER = ROOT / "scripts/run-issue-agent.py"


def shell(filename, step, replacements=None):
    text = (ROOT / ".github/workflows" / filename).read_text()
    block = text.split(f"      - name: {step}\n", 1)[1].split("        run: |\n", 1)[1]
    lines = []
    for line in block.splitlines():
        if line and not line.startswith("          "):
            break
        lines.append(line[10:])
    return re.sub(
        r"\$\{\{\s*(.*?)\s*\}\}",
        lambda m: (replacements or {}).get(m[1], ""),
        "\n".join(lines),
    )


def run_agent(
    tmp_path,
    *,
    workflow=None,
    event="success",
    exit_code=0,
    router="router-secret",
    legacy="",
    model="",
    timeout="10",
):
    cli = tmp_path / "opencode"
    cli.write_text(f"#!{sys.executable}\n" + """import json, os, pathlib, sys, time
payload = sys.stdin.read()
pathlib.Path(os.environ['CAPTURE']).write_text(json.dumps({'argv':sys.argv[1:], 'stdin':payload,
 'env':{k:os.environ.get(k) for k in ['AGENT_API_KEY','OPENROUTER_API_KEY','ANTHROPIC_API_KEY','OPENAI_API_KEY','HOME','XDG_DATA_HOME','OPENCODE_DB']}}))
if os.environ['EVENT'] == 'timeout': time.sleep(10)
if os.environ['EVENT'] == 'error':
 print(json.dumps({'type':'error','error':{'message':'provider unavailable'}}))
elif os.environ['EVENT'] == 'malformed': print('not an event')
elif os.environ['EVENT'] == 'success':
 print(json.dumps({'type':'text','part':{'text':'Implemented the requested change'}}))
 print(json.dumps({'type':'step_finish','part':{'reason':'stop'}}))
sys.exit(int(os.environ['CLI_EXIT']))
""")
    cli.chmod(0o755)
    prompt = tmp_path / "agent_prompt.txt"
    prompt.write_text("Implement this issue:\n" + "x" * 300_000)
    shutil.copy(RUNNER, tmp_path / "run-issue-agent.py")
    env = {k: v for k, v in os.environ.items() if not k.endswith("API_KEY")}
    env.update(
        AGENT_CLI=str(cli),
        AGENT_MODEL=model,
        AGENT_CLI_FLAGS='--title "two words"',
        OPENROUTER_API_KEY=router,
        AGENT_API_KEY=legacy,
        AGENT_TIMEOUT_SECONDS=timeout,
        EVENT=event,
        CLI_EXIT=str(exit_code),
        CAPTURE=str(tmp_path / "capture.json"),
        RUNNER_TEMP=str(tmp_path),
        GITHUB_ENV=str(tmp_path / "github_env"),
        HOME="/shared/home",
        XDG_DATA_HOME="/shared/data",
        OPENCODE_DB="/shared/db",
    )
    command = (
        ["bash", "-c", shell(workflow, "Run Agent")]
        if workflow
        else [sys.executable, str(RUNNER), "--prompt", str(prompt)]
    )
    result = subprocess.run(
        command, env=env, cwd=tmp_path, capture_output=True, text=True
    )
    capture = (
        json.loads((tmp_path / "capture.json").read_text())
        if (tmp_path / "capture.json").exists()
        else None
    )
    return result, capture


@pytest.mark.parametrize(
    "workflow", ["agent-issue-solver.yml", "agent-parallel-solver.yml"]
)
def test_both_workflows_invoke_real_helper_with_router_secret_and_large_stdin(
    tmp_path, workflow
):
    result, capture = run_agent(tmp_path, workflow=workflow)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "github_env").read_text() == "agent_exit_code=0\n"
    assert capture["argv"][:3] == ["run", "--format", "json"]
    assert (
        "--non-interactive" not in capture["argv"] and "--prompt" not in capture["argv"]
    )
    assert len(capture["stdin"]) > 300_000
    assert all(len(arg) < 1000 for arg in capture["argv"])
    assert "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free" in capture["argv"]
    assert "two words" in capture["argv"]
    assert capture["env"]["OPENROUTER_API_KEY"] == "router-secret"
    assert capture["env"]["OPENAI_API_KEY"] is None
    assert capture["env"]["HOME"] != "/shared/home"
    assert capture["env"]["XDG_DATA_HOME"] != "/shared/data"
    assert capture["env"]["OPENCODE_DB"] is None
    assert "router-secret" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "event,exit_code", [("error", 0), ("malformed", 0), ("empty", 0), ("success", 3)]
)
def test_provider_errors_and_incomplete_or_failed_runs_fail_closed(
    tmp_path, event, exit_code
):
    result, _ = run_agent(tmp_path, event=event, exit_code=exit_code)
    assert result.returncode != 0


def test_missing_credentials_fail_before_launch(tmp_path):
    result, capture = run_agent(tmp_path, router="", legacy="")
    assert result.returncode == 2 and capture is None


def test_router_key_preferred_and_legacy_fallback_supported(tmp_path):
    result, capture = run_agent(tmp_path, legacy="legacy-secret")
    assert result.returncode == 0
    assert capture["env"]["OPENROUTER_API_KEY"] == "router-secret"
    other = tmp_path / "fallback"
    other.mkdir()
    result, capture = run_agent(other, router="", legacy="legacy-secret")
    assert result.returncode == 0
    assert capture["env"]["OPENROUTER_API_KEY"] == "legacy-secret"


def test_native_provider_does_not_receive_router_key(tmp_path):
    result, capture = run_agent(
        tmp_path, legacy="anthropic-secret", model="anthropic/test"
    )
    assert result.returncode == 0
    assert capture["env"]["ANTHROPIC_API_KEY"] == "anthropic-secret"
    assert capture["env"]["OPENROUTER_API_KEY"] is None


def test_timeout_is_bounded_and_reports_failure(tmp_path):
    result, _ = run_agent(tmp_path, event="timeout", timeout="1")
    assert result.returncode == 124


def test_failed_cli_exit_is_preserved_by_workflow(tmp_path):
    result, _ = run_agent(tmp_path, workflow="agent-issue-solver.yml", event="error")
    assert result.returncode == 0  # workflow records the result for label cleanup
    assert (tmp_path / "github_env").read_text() == "agent_exit_code=1\n"
    workflow = (ROOT / ".github/workflows/agent-issue-solver.yml").read_text()
    commit = workflow.split("      - name: Commit and Push\n")[1].split(
        "        run: |"
    )[0]
    assert "env.agent_exit_code == '0'" in commit
    assert "      - name: Propagate Failure" in workflow


@pytest.mark.parametrize(
    "workflow", ["agent-issue-solver.yml", "agent-parallel-solver.yml"]
)
def test_prompt_composition_does_not_dirty_checkout(tmp_path, workflow):
    gh = tmp_path / "gh"
    gh.write_text('#!/bin/sh\nprintf \'{"title":"Issue","body":"Description"}\\n\'\n')
    gh.chmod(0o755)
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (checkout / "AGENTS.md").write_text("Repository instructions")
    result = subprocess.run(
        ["bash", "-c", shell(workflow, "Compose Prompt")],
        cwd=checkout,
        env=dict(
            os.environ,
            PATH=str(tmp_path) + os.pathsep + os.environ["PATH"],
            REPO="owner/repo",
            ISSUE_NUMBER="97",
            RUNNER_TEMP=str(runtime),
            GITHUB_OUTPUT=str(tmp_path / "outputs"),
        ),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert not (checkout / "agent_prompt.txt").exists()
    assert "Description" in (runtime / "agent_prompt.txt").read_text()


@pytest.mark.parametrize("label", ["agent-failed", "agent-pr"])
def test_parallel_failure_publishes_only_a_draft_without_claiming_resolution(
    tmp_path, label
):
    cli = tmp_path / "gh"
    cli.write_text(f"#!{sys.executable}\n" + """import json, os, pathlib, sys
with open(os.environ['CAPTURE'], 'a') as out: out.write(json.dumps(sys.argv[1:])+'\\n')
if sys.argv[1:3] == ['issue','view']: print('Example issue')
""")
    cli.chmod(0o755)
    result = subprocess.run(
        [
            "bash",
            "-c",
            shell(
                "agent-parallel-solver.yml",
                "Create or Update Pull Request",
                {"steps.status.outputs.label": label},
            ),
        ],
        cwd=tmp_path,
        env=dict(
            os.environ,
            PATH=str(tmp_path) + os.pathsep + os.environ["PATH"],
            CAPTURE=str(tmp_path / "calls"),
            REPO="owner/repo",
            ISSUE_NUMBER="97",
        ),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    calls = [json.loads(line) for line in (tmp_path / "calls").read_text().splitlines()]
    create = next(call for call in calls if call[:2] == ["pr", "create"])
    body = create[create.index("--body") + 1]
    if label == "agent-failed":
        assert "--draft" in create and "Closes #" not in body
        assert "not a verified solution" in body
    else:
        assert "--draft" not in create and "Closes #97" in body


@pytest.mark.parametrize(
    "state,working,expected",
    [("open", False, 0), ("closed", False, 1), ("open", True, 1)],
)
def test_explicit_retry_checks_live_issue_state(tmp_path, state, working, expected):
    cli = tmp_path / "gh"
    data = {"state": state, "labels": [{"name": "agent-working"}] if working else []}
    cli.write_text(f"#!{sys.executable}\nprint({json.dumps(json.dumps(data))})\n")
    cli.chmod(0o755)
    result = subprocess.run(
        [
            "bash",
            "-c",
            shell(
                "agent-issue-solver.yml",
                "Identify issue",
                {"github.event_name": "workflow_dispatch"},
            ),
        ],
        cwd=tmp_path,
        env=dict(
            os.environ,
            PATH=str(tmp_path) + os.pathsep + os.environ["PATH"],
            TARGET_ISSUE="97",
            REPO="owner/repo",
            GITHUB_OUTPUT=str(tmp_path / "outputs"),
        ),
        capture_output=True,
        text=True,
    )
    assert result.returncode == expected, result.stderr
    if not expected:
        assert (tmp_path / "outputs").read_text() == "issue_number=97\n"


@pytest.mark.parametrize("mode", ["unchanged", "uncommitted", "committed"])
def test_publication_requires_actual_work_and_handles_agent_commits(tmp_path, mode):
    repo = tmp_path / "repo"
    repo.mkdir()
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
        ).stdout.strip()

    git("init", "-q")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.invalid")
    (repo / "base.txt").write_text("base")
    git("add", ".")
    git("commit", "-qm", "baseline")
    base = git("rev-parse", "HEAD")
    git("remote", "add", "origin", str(remote))
    git("checkout", "-b", "feat/agent-97-123")
    if mode != "unchanged":
        (repo / "solution.py").write_text('print("implemented")\n')
    if mode == "committed":
        git("add", ".")
        git("commit", "-qm", "agent implementation")
    output = tmp_path / "outputs"
    result = subprocess.run(
        [
            "bash",
            "-c",
            shell(
                "agent-issue-solver.yml",
                "Commit and Push",
                {"steps.identify.outputs.issue_number": "97"},
            ),
        ],
        cwd=repo,
        env=dict(
            os.environ,
            GITHUB_RUN_ID="123",
            AGENT_BASE_SHA=base,
            GITHUB_OUTPUT=str(output),
        ),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert output.read_text() == (
        "changes=false\n" if mode == "unchanged" else "changes=true\n"
    )
