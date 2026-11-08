"""Exercise the actual review workflow shell without calling a model provider."""

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


def workflow_shell(filename, step_name, replacements=None):
    """Extract one literal run block without requiring a YAML runtime dependency."""
    text = (ROOT / ".github/workflows" / filename).read_text()
    step = text.split(f"      - name: {step_name}\n", 1)[1]
    run = step.split("        run: |\n", 1)[1]
    lines = []
    for line in run.splitlines():
        if line and not line.startswith("          "):
            break
        lines.append(line[10:])
    script = "\n".join(lines) + "\n"
    values = replacements or {}
    return re.sub(r"\$\{\{\s*(.*?)\s*\}\}", lambda m: values.get(m[1], ""), script)


def run_review(
    tmp_path,
    workflow,
    *,
    mode="",
    cli_exit=0,
    large=True,
    prefix="",
    model="openrouter/test",
    picker=False,
):
    if picker:
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        shutil.copy(ROOT / "scripts/run-review-models.py", scripts)
        package = tmp_path / "src/liminal_bridge"
        package.mkdir(parents=True)
        (package / "__init__.py").touch()
        (package / "model_picker.py").write_text(
            'def get_model_candidates(kind): return ["selected/best:free"]\n'
        )
    cli = tmp_path / "opencode"
    cli.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        'pathlib.Path("received.json").write_text(json.dumps({"argv": sys.argv[1:], '
        '"stdin": sys.stdin.read()}))\n'
        'print(os.environ.get("FAKE_OUTPUT_PREFIX", ""), end="")\n'
        'text = "## Summary\\nReview captured\\nREVIEW_RESULT: '
        '{\\"verdict\\":\\"PASS\\",\\"blocking_findings\\":0}"\n'
        'print(json.dumps({"type": "text", "part": {"text": text}}) '
        'if "--format" in sys.argv else text)\n'
        'sys.exit(int(os.environ["FAKE_CLI_EXIT"]))\n'
    )
    cli.chmod(0o755)
    patch = "diff --git a/example b/example\n+" + "x" * (300_000 if large else 100)
    (tmp_path / "pr_patch.diff").write_text(patch)
    (tmp_path / "agent_prompt.txt").write_text("Review this:\n" + patch)
    (tmp_path / "review_pr.json").write_text(
        json.dumps({"labels": [{"name": "decision-merge"}]})
    )
    replacements = {
        "steps.install.outputs.cli_binary": str(cli),
        "steps.resolve.outputs.agent_cli_lower": "opencode",
        "steps.resolve.outputs.agent_model_flag": "--model",
        "steps.resolve.outputs.agent_prompt_flag": "--prompt",
        "steps.resolve.outputs.agent_prompt_mode": mode,
    }
    step = "Run Review CLI" if workflow == "opencode.yml" else "Run Agent"
    script = workflow_shell(workflow, step, replacements)
    environment = dict(
        os.environ,
        REVIEW_PROMPT="Review this:",
        MODEL=model,
        GITHUB_OUTPUT=str(tmp_path / "outputs"),
        AGENT_CLI=str(cli),
        AGENT_CLI_FLAGS="",
        AGENT_MODEL=model,
        AGENT_API_KEY="",
        AGENT_PROMPT_MODE=mode,
        FAKE_CLI_EXIT=str(cli_exit),
        FAKE_OUTPUT_PREFIX=prefix,
    )
    # The dispatch workflow selects providers by the configured binary name.
    if workflow != "opencode.yml":
        environment["AGENT_CLI"] = "opencode"
        environment["PATH"] = str(tmp_path) + os.pathsep + environment["PATH"]
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )
    return result, json.loads((tmp_path / "received.json").read_text()), patch


@pytest.mark.parametrize("workflow", ["opencode.yml", "workflow-review-dispatch.yml"])
def test_large_review_uses_stdin_with_bounded_arguments(tmp_path, workflow):
    result, received, patch = run_review(tmp_path, workflow)
    assert result.returncode == 0, result.stderr
    assert patch in received["stdin"]
    assert sum(map(len, received["argv"])) < 1024
    assert "exit_code=0" in (tmp_path / "outputs").read_text()
    if workflow == "opencode.yml":
        assert "REVIEW_RESULT:" in received["stdin"]
        assert "Never return PASS merely" in received["stdin"]


@pytest.mark.parametrize("workflow", ["opencode.yml", "workflow-review-dispatch.yml"])
def test_cli_failure_is_reported_and_output_preserved(tmp_path, workflow):
    result, _, _ = run_review(tmp_path, workflow, cli_exit=42)
    assert result.returncode == 42, result.stderr
    assert "exit_code=42" in (tmp_path / "outputs").read_text()
    assert "Review captured" in (tmp_path / "review_output.txt").read_text()


@pytest.mark.parametrize("workflow", ["opencode.yml", "workflow-review-dispatch.yml"])
@pytest.mark.parametrize("mode", ["positional", "flag"])
def test_explicit_legacy_prompt_mode_is_preserved(tmp_path, workflow, mode):
    result, received, patch = run_review(tmp_path, workflow, mode=mode, large=False)
    assert result.returncode == 0, result.stderr
    assert received["stdin"] == ""
    assert patch in received["argv"][-1]
    assert ("--prompt" in received["argv"]) == (mode == "flag")


def test_multibyte_review_comment_uses_file_with_bounded_arguments(tmp_path):
    content = "## Summary\n" + "語" * 50_000
    (tmp_path / "review_output.txt").write_text(content)
    gh = tmp_path / "gh"
    gh.write_text(
        f"#!{sys.executable}\n"
        "import json, pathlib, sys\n"
        "args = sys.argv[1:]\n"
        'body = pathlib.Path(args[args.index("--body-file") + 1]).read_text()\n'
        'pathlib.Path("posted.json").write_text(json.dumps({"argv": args, "body": body}))\n'
    )
    gh.chmod(0o755)
    script = workflow_shell(
        "opencode.yml",
        "Post Review Result",
        {
            "steps.prep.outputs.pr_number": "86",
            "steps.resolve.outputs.agent_cli": "opencode",
            "steps.resolve.outputs.selection_source": "default",
            "steps.run_cli.outputs.exit_code": "0",
        },
    )
    environment = dict(
        os.environ,
        PATH=str(tmp_path) + os.pathsep + os.environ["PATH"],
        REPO="owner/repo",
        MODEL="openrouter/test",
        LC_ALL="C.UTF-8",
    )
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    posted = json.loads((tmp_path / "posted.json").read_text())
    assert content in posted["body"]
    assert len(posted["body"].encode()) > 128 * 1024
    assert sum(map(len, posted["argv"])) < 1024
    assert "--body" not in posted["argv"]


def test_evidence_preserves_conflicting_marker_before_markdown(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "review_result", ROOT / "src/liminal_bridge/review_result.py"
    )
    verdicts = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verdicts)

    prefix = 'REVIEW_RESULT: {"verdict":"FAIL","blocking_findings":1}\n'
    result, _, _ = run_review(tmp_path, "opencode.yml", prefix=prefix)
    assert result.returncode == 0, result.stderr
    complete_output = (tmp_path / "review_output_clean.txt").read_text()
    assert complete_output.startswith(prefix)
    assert complete_output.count("REVIEW_RESULT:") == 2
    assert not verdicts.review_passed(complete_output)
    producer = workflow_shell("opencode.yml", "Validate immutable review evidence")
    assert "--review review_output_clean.txt" in producer


@pytest.mark.parametrize("workflow", ["opencode.yml", "workflow-review-dispatch.yml"])
def test_auto_bootstrap_uses_trusted_fixed_model_until_base_merge(tmp_path, workflow):
    result, received, _ = run_review(tmp_path, workflow, model="auto")
    assert result.returncode == 0, result.stderr
    assert "trusted-base merge" in result.stdout
    assert "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free" in received["argv"]
    assert (
        "model=openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"
        in (tmp_path / "outputs").read_text()
    )


@pytest.mark.parametrize("workflow", ["opencode.yml", "workflow-review-dispatch.yml"])
def test_auto_dynamic_helper_records_actual_chosen_model(tmp_path, workflow):
    result, received, patch = run_review(tmp_path, workflow, model="auto", picker=True)
    assert result.returncode == 0, result.stderr
    assert "openrouter/selected/best:free" in received["argv"]
    assert "--format" in received["argv"]
    assert patch in received["stdin"]
    assert "model=openrouter/selected/best:free" in (tmp_path / "outputs").read_text()
    assert "Review captured" in (tmp_path / "review_output.txt").read_text()
