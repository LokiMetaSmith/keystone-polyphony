"""Review evidence must bind successful analysis to one immutable PR snapshot."""

import copy
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest

SPEC = importlib.util.spec_from_file_location(
    "review_evidence", Path(__file__).parents[1] / "scripts/write-review-evidence.py"
)
evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evidence)


@pytest.fixture
def pr():
    return {
        "number": 86,
        "state": "open",
        "merged": False,
        "head": {"sha": "a" * 40},
        "base": {"sha": "b" * 40, "repo": {"full_name": "owner/repo"}},
    }


def build(
    pr, current=None, review=b"## Summary\nSafe\n## Recommendation\nGo", **overrides
):
    arguments = dict(
        repository="owner/repo",
        run_id=123,
        run_attempt=2,
        workflow_path=".github/workflows/opencode.yml",
        model="review/model",
        scope="general",
        exit_code=0,
    )
    arguments.update(overrides)
    return evidence.build_evidence(
        pr, current or copy.deepcopy(pr), review, **arguments
    )


def test_schema_binds_exact_revisions_and_run(pr):
    result = build(pr)
    assert result == {
        "version": 1,
        "repository": "owner/repo",
        "pr_number": 86,
        "head_sha": "a" * 40,
        "base_sha": "b" * 40,
        "run_id": 123,
        "run_attempt": 2,
        "workflow_path": ".github/workflows/opencode.yml",
        "model": "review/model",
        "review_text": "## Summary\nSafe\n## Recommendation\nGo",
        "exit_code": 0,
        "scope": "general",
    }


@pytest.mark.parametrize("side", ["head", "base"])
def test_rejects_stale_revisions(pr, side):
    current = copy.deepcopy(pr)
    current[side]["sha"] = "c" * 40
    with pytest.raises(ValueError, match="changed"):
        build(pr, current)


@pytest.mark.parametrize(
    "overrides",
    [
        dict(exit_code=1),
        dict(run_id=0),
        dict(run_attempt=0),
        dict(model=""),
        dict(scope="unknown"),
        dict(workflow_path="untrusted.yml"),
        dict(repository="other/repo"),
    ],
)
def test_rejects_invalid_identity_or_failed_cli(pr, overrides):
    with pytest.raises(ValueError):
        build(pr, **overrides)


@pytest.mark.parametrize(
    "review",
    [
        b"",
        b"   ",
        b"No output captured from review CLI.",
        b"## Summary\x00bad",
        b"## Summary\xff",
        b"# " + b"x" * 60000,
    ],
)
def test_rejects_empty_malformed_and_oversized_output(pr, review):
    with pytest.raises((ValueError, UnicodeDecodeError)):
        build(pr, review=review)


def test_unicode_bound_is_bytes_and_json_remains_inert(pr):
    text = "## Summary\n" + "ö" * 29995
    with pytest.raises(ValueError, match="oversized"):
        build(pr, review=text.encode())
    text = "## Summary\nUnicode ✓ and `$(touch /tmp/no)` are data"
    assert (
        json.loads(json.dumps(build(pr, review=text.encode())))["review_text"] == text
    )


@pytest.mark.parametrize("mutation", ["closed", "merged", "number", "sha"])
def test_rejects_invalid_pr_state(pr, mutation):
    current = copy.deepcopy(pr)
    if mutation == "closed":
        current["state"] = "closed"
    elif mutation == "merged":
        current["merged"] = True
    elif mutation == "number":
        current["number"] = 99
    else:
        current["head"]["sha"] = "garbage"
    with pytest.raises(ValueError):
        build(pr, current)


def test_main_removes_existing_evidence_before_recheck_failure(
    pr, tmp_path, monkeypatch
):
    snapshot = tmp_path / "pr.json"
    snapshot.write_text(json.dumps(pr))
    review = tmp_path / "review.txt"
    review.write_text("## Summary\nGo")
    output = tmp_path / "review-evidence.json"
    output.write_text("old evidence")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")
    current = copy.deepcopy(pr)
    current["head"]["sha"] = "c" * 40
    with patch(
        "sys.argv",
        [
            "write-review-evidence.py",
            "--snapshot",
            str(snapshot),
            "--review",
            str(review),
            "--output",
            str(output),
            "--scope",
            "general",
            "--model",
            "review/model",
            "--exit-code",
            "0",
            "--workflow-path",
            ".github/workflows/opencode.yml",
        ],
    ), patch.object(evidence.subprocess, "run") as run:
        run.return_value.stdout = json.dumps(current)
        with pytest.raises(ValueError, match="changed"):
            evidence.main()
        run.assert_called_once_with(
            ["gh", "api", "/repos/owner/repo/pulls/86"],
            check=True,
            capture_output=True,
            text=True,
        )
    assert not output.exists()
