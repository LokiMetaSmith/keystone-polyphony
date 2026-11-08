"""Provider failover must never turn a rejected review into model shopping."""

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

SPEC = importlib.util.spec_from_file_location(
    "review_model_runner", Path(__file__).parents[1] / "scripts/run-review-models.py"
)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def event(kind, **fields):
    return json.dumps({"type": kind, **fields}) + "\n"


def result(text="", code=0):
    return subprocess.CompletedProcess([], code, text.encode(), b"")


def args(tmp_path):
    prompt = tmp_path / "prompt"
    prompt.write_text("large patch " * 30_000)
    return argparse.Namespace(
        command=["--", "opencode", "run", "--model", "auto", "Review stdin"],
        model_flag="--model",
        model_output=str(tmp_path / "selected"),
        stdin_file=str(prompt),
        json_events=True,
        timeout=240,
    )


@pytest.mark.parametrize(
    "first",
    [
        result(event("error", error={"name": "APIError"})),
        result("", 1),
        result(""),
    ],
)
def test_provider_failure_tries_next_model_and_reopens_stdin(
    tmp_path, monkeypatch, first, capsys
):
    calls = []
    responses = [first, result(event("text", part={"text": "## Summary\nGO"}))]

    def invoke(command, **kwargs):
        calls.append((list(command), kwargs["stdin"].read()))
        return responses.pop(0)

    monkeypatch.setattr(runner.subprocess, "run", invoke)
    options = args(tmp_path)
    assert runner.run(options, ["first:free", "second:free"]) == 0
    assert [call[0][3] for call in calls] == [
        "openrouter/first:free",
        "openrouter/second:free",
    ]
    assert calls[0][1] == calls[1][1]
    assert len(calls[0][1]) > 128 * 1024
    assert all(sum(map(len, call[0])) < 1024 for call in calls)
    assert Path(options.model_output).read_text().strip() == "openrouter/second:free"
    assert capsys.readouterr().out == "## Summary\nGO\n"


@pytest.mark.parametrize("exit_code", [0, 1])
def test_completed_failed_review_never_advances(
    tmp_path, monkeypatch, exit_code, capsys
):
    calls = []
    rejection = 'REVIEW_RESULT: {"verdict":"FAIL","blocking_findings":1}'

    def invoke(command, **kwargs):
        calls.append(command)
        return result(event("text", part={"text": rejection}), exit_code)

    monkeypatch.setattr(runner.subprocess, "run", invoke)
    assert runner.run(args(tmp_path), ["first:free", "second:free"]) == exit_code
    assert len(calls) == 1
    assert rejection in capsys.readouterr().out


def test_tool_failure_is_recoverable_and_not_provider_failure(
    tmp_path, monkeypatch, capsys
):
    output = event(
        "tool_use", part={"state": {"status": "error", "error": "Missing file"}}
    )
    output += event("text", part={"text": "## Summary\nGO"})
    calls = []

    def invoke(command, **kwargs):
        calls.append(command)
        return result(output)

    monkeypatch.setattr(runner.subprocess, "run", invoke)
    assert runner.run(args(tmp_path), ["first:free", "second:free"]) == 0
    assert len(calls) == 1
    assert "GO" in capsys.readouterr().out


def test_timeout_attempts_are_bounded(tmp_path, monkeypatch):
    calls = []

    def invoke(command, **kwargs):
        calls.append(command)
        assert kwargs["timeout"] == 240
        raise subprocess.TimeoutExpired(command, 240)

    monkeypatch.setattr(runner.subprocess, "run", invoke)
    assert runner.run(args(tmp_path), ["a:free", "b:free", "c:free", "d:free"]) == 124
    assert len(calls) == 3


def test_error_plus_verdict_fails_closed_without_retry(tmp_path, monkeypatch):
    calls = []
    output = event("error") + event(
        "text", part={"text": 'REVIEW_RESULT: {"verdict":"PASS","blocking_findings":0}'}
    )

    def invoke(command, **kwargs):
        calls.append(command)
        return result(output)

    monkeypatch.setattr(runner.subprocess, "run", invoke)
    assert runner.run(args(tmp_path), ["a:free", "b:free"]) == 1
    assert len(calls) == 1
