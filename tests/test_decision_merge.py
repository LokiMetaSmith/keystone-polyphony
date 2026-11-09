import importlib.util
import io
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import zipfile

import pytest

SPEC = importlib.util.spec_from_file_location(
    "decision_merge", Path(__file__).resolve().parents[1] / "scripts/decision-merge.py"
)
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)
HEAD = "a" * 40
BASE = "b" * 40
MERGE = "c" * 40
REPO = "owner/repo"


def archive(data, name="review-evidence.json"):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as zipped:
        zipped.writestr(name, json.dumps(data))
    return stream.getvalue()


@pytest.fixture
def evidence():
    return {
        "version": 2,
        "repository": REPO,
        "pr_number": 8,
        "head_sha": HEAD,
        "base_sha": BASE,
        "exit_code": 0,
        "scope": "general",
        "review_text": '## Recommendation\nGO: no findings.\nREVIEW_RESULT: {"verdict":"PASS","blocking_findings":0}',
        "review_verdict": "PASS",
        "blocking_findings": 0,
        "run_id": 90,
        "run_attempt": 1,
        "workflow_path": ".github/workflows/opencode.yml",
        "model": "review-model",
    }


@pytest.fixture
def pr():
    return {
        "number": 8,
        "state": "open",
        "draft": False,
        "mergeable": True,
        "head": {"sha": HEAD},
        "base": {"sha": BASE, "ref": "main", "repo": {"full_name": REPO}},
        "labels": [{"name": "decision-merge"}],
        "merge_commit_sha": MERGE,
    }


def test_archive_is_json_data_only(evidence):
    assert gate.artifact_json(archive(evidence)) == evidence


@pytest.mark.parametrize(
    "name", ["../review-evidence.json", "nested/review-evidence.json", "run.py"]
)
def test_unexpected_archive_paths_rejected(evidence, name):
    with pytest.raises(gate.Hold):
        gate.artifact_json(archive(evidence, name))


def test_zip_bomb_and_duplicate_entries_rejected():
    with pytest.raises(gate.Hold):
        gate.artifact_json(archive("x" * (gate.MAX_ARTIFACT + 1)))
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as zipped:
        zipped.writestr("review-evidence.json", "{}")
        zipped.writestr("other.txt", "ignored")
    with pytest.raises(gate.Hold):
        gate.artifact_json(stream.getvalue())


def test_review_workflow_cannot_certify_modified_copy(evidence, pr):
    github = Mock()
    github.api.side_effect = [{"sha": "trusted"}, {"sha": "changed"}]
    with pytest.raises(gate.Hold, match="differs from trusted"):
        gate.verify_workflow(github, {"head_sha": HEAD}, evidence, pr)


@pytest.mark.parametrize("mutation", ["run_attempt", "workflow_path", "repository"])
def test_artifact_provenance_rejected(evidence, mutation):
    github = Mock(repository=REPO)
    run = {
        "name": "opencode",
        "path": evidence["workflow_path"],
        "status": "completed",
        "conclusion": "success",
        "repository": {"full_name": REPO},
        "run_attempt": 1,
    }
    altered = dict(evidence, **{mutation: "wrong"})
    github.api.side_effect = [run, archive(altered)]
    github.pages.return_value = [
        {
            "id": 7,
            "name": "decision-review-90-1",
            "size_in_bytes": 1000,
            "expired": False,
        }
    ]
    with pytest.raises(gate.Hold, match="provenance"):
        gate.read_evidence(github, 90)


def test_workflow_review_scope_cannot_cover_application_code(evidence, pr):
    github = Mock()
    github.pages.return_value = [{"filename": "src/app.py", "patch": "@@ test"}]
    with pytest.raises(gate.Hold, match="Workflow-only"):
        gate.fetch_diff(github, pr, {**evidence, "scope": "workflow"})
    github.api.assert_not_called()


def test_missing_and_oversized_diff_held(evidence, pr):
    github = Mock()
    github.pages.return_value = [{"filename": "image.png"}]
    with pytest.raises(gate.Hold, match="Complete text"):
        gate.fetch_diff(github, pr, evidence)
    github.pages.return_value = [{"filename": "src/app.py", "patch": "@@ test"}]
    github.api.return_value = b"x" * (gate.MAX_DIFF + 1)
    with pytest.raises(gate.Hold, match="budget"):
        gate.fetch_diff(github, pr, evidence)


@pytest.fixture
def ready_github(monkeypatch, pr):
    github = Mock(repository=REPO)
    github.api.return_value = pr

    def pages(path, key=None):
        if "/runs?" in path:
            return [{"id": 91}]
        if f"commits/{MERGE}/check-runs" in path:
            return [
                {
                    "name": "pr-validation",
                    "status": "completed",
                    "conclusion": "success",
                }
            ]
        if "/check-runs" in path:
            return [
                {"name": "review", "status": "completed", "conclusion": "success"},
                {
                    "name": "decision-gate",
                    "app": {"slug": "github-actions"},
                    "status": "in_progress",
                    "details_url": f"https://github.com/{REPO}/actions/runs/91/job/1",
                },
            ]
        return []

    github.pages.side_effect = pages
    monkeypatch.setattr(gate, "unresolved_threads", lambda *args: False)
    return github


def test_validation_on_current_merge_commit_counts(ready_github, evidence):
    pr, checks = gate.readiness(ready_github, 8, evidence, ["pr-validation"])
    assert pr["head"]["sha"] == HEAD
    assert [item["name"] for item in checks] == ["pr-validation"]


def test_review_success_alone_does_not_count(ready_github, evidence):
    old_pages = ready_github.pages.side_effect
    ready_github.pages.side_effect = lambda path, key=None: (
        [] if f"commits/{MERGE}/check-runs" in path else old_pages(path, key)
    )
    with pytest.raises(gate.Hold, match="successful_validation"):
        gate.readiness(ready_github, 8, evidence, [])


def test_failed_review_cannot_reach_even_an_approving_decision_model(
    ready_github, evidence, monkeypatch
):
    evidence["review_text"] = (
        '## Recommendation\nNO GO\nREVIEW_RESULT: {"verdict":"FAIL","blocking_findings":1}'
    )
    # A forged PASS metadata field cannot override the actual reviewer output.
    monkeypatch.setattr(
        gate, "read_evidence", lambda *args: ({"head_sha": HEAD}, evidence)
    )
    remote = AsyncMock(return_value={"approved": True, "confidence": 0.99})
    monkeypatch.setattr(gate, "evaluate_review", remote)
    apply = Mock()
    monkeypatch.setattr(gate, "approve_and_stage", apply)
    with pytest.raises(gate.Hold, match="automatic_review_not_passed"):
        gate.evaluate(ready_github, 90, dry_run=False)
    remote.assert_not_awaited()
    apply.assert_not_called()


@pytest.fixture
def evaluate_ready(monkeypatch, evidence, pr):
    github = Mock(repository=REPO)
    monkeypatch.setattr(
        gate, "read_evidence", lambda *args: ({"head_sha": HEAD}, evidence)
    )
    monkeypatch.setattr(
        gate,
        "readiness",
        Mock(return_value=(pr, [{"name": "test", "conclusion": "success"}])),
    )
    monkeypatch.setattr(gate, "verify_workflow", Mock())
    monkeypatch.setattr(gate, "is_staged", lambda *args: False)
    monkeypatch.setattr(
        gate, "fetch_diff", lambda *args: "diff --git a/test b/test\n+fix"
    )
    monkeypatch.setattr(
        gate,
        "evaluate_review",
        AsyncMock(
            return_value={
                "approved": True,
                "status": "decision",
                "confidence": 0.99,
                "model": "decision-model",
            }
        ),
    )
    monkeypatch.setattr(gate, "approve_and_stage", Mock())
    return github


def test_dry_run_has_no_approval_or_push(evaluate_ready):
    result = gate.evaluate(evaluate_ready, 90, dry_run=True)
    assert result["status"] == "would_stage"
    gate.approve_and_stage.assert_not_called()


def test_remote_hold_never_applies(evaluate_ready):
    gate.evaluate_review.return_value = {
        "approved": False,
        "status": "low_confidence",
        "confidence": None,
    }
    assert gate.evaluate(evaluate_ready, 90, dry_run=False)["status"] == "held"
    gate.approve_and_stage.assert_not_called()


def test_head_change_during_remote_decision_stops_apply(evaluate_ready):
    gate.readiness.side_effect = [({"number": 8}, []), gate.Hold("head_sha_mismatch")]
    with pytest.raises(gate.Hold, match="head_sha"):
        gate.evaluate(evaluate_ready, 90, dry_run=False)
    gate.approve_and_stage.assert_not_called()


def test_accepted_decision_applies_only_reviewed_evidence(evaluate_ready, evidence):
    result = gate.evaluate(evaluate_ready, 90, dry_run=False)
    assert result["status"] == "staged"
    assert gate.approve_and_stage.call_args.args[2] == evidence


def test_staging_uses_exact_sha_normal_merge_and_push(monkeypatch, evidence, pr):
    github = Mock(repository=REPO)
    github.pages.return_value = []
    calls = []

    def git(directory, *args, **kwargs):
        calls.append(args)
        if args[0] == "rev-parse":
            return HEAD
        if args[0] == "ls-remote":
            return "existing-staging"
        return ""

    monkeypatch.setattr(gate, "git_run", git)
    monkeypatch.setattr(gate, "readiness", Mock())
    monkeypatch.setenv("GH_TOKEN", "test-token")
    gate.approve_and_stage(
        github, pr, evidence, {"model": "test", "confidence": 0.99}, []
    )
    assert ("merge", "--no-ff", "--no-edit", HEAD) in calls
    assert any(
        "push" in args and args[-1] == "HEAD:refs/heads/staging" for args in calls
    )
    assert not any("--force" in args or "-X" in args for args in calls)
    approval = github.api.call_args.kwargs["body"]
    assert approval["commit_id"] == HEAD and approval["event"] == "APPROVE"


def test_final_recheck_prevents_push_after_approval(monkeypatch, evidence, pr):
    github = Mock(repository=REPO)
    github.pages.return_value = []
    calls = []

    def git(directory, *args, **kwargs):
        calls.append(args)
        return HEAD if args[0] == "rev-parse" else ""

    monkeypatch.setattr(gate, "git_run", git)
    monkeypatch.setattr(
        gate, "readiness", Mock(side_effect=[None, gate.Hold("head_sha_mismatch")])
    )
    with pytest.raises(gate.Hold, match="head_sha"):
        gate.approve_and_stage(
            github, pr, evidence, {"model": "test", "confidence": 0.99}, []
        )
    assert not any("push" in args for args in calls)


def test_merge_conflict_prevents_approval_and_push(monkeypatch, evidence, pr):
    github = Mock(repository=REPO)
    calls = []

    def git(directory, *args, **kwargs):
        calls.append(args)
        if args[0] == "merge":
            raise gate.Hold("conflict")
        return HEAD if args[0] == "rev-parse" else ""

    monkeypatch.setattr(gate, "git_run", git)
    with pytest.raises(gate.Hold, match="conflict"):
        gate.approve_and_stage(
            github, pr, evidence, {"model": "test", "confidence": 0.99}, []
        )
    github.api.assert_not_called()
    assert not any("push" in args for args in calls)


def test_real_git_admission_to_local_staging(monkeypatch, tmp_path, evidence, pr):
    """Exercise fetch/merge/push against a local bare remote, without GitHub writes."""
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"

    def git(*args, cwd=tmp_path):
        return subprocess.run(
            ["git", *args], cwd=cwd, check=True, text=True, capture_output=True
        ).stdout.strip()

    git("init", "--bare", str(remote))
    git("init", str(work))
    git("config", "user.name", "Test", cwd=work)
    git("config", "user.email", "test@example.invalid", cwd=work)
    (work / "example.txt").write_text("base\n")
    git("add", "example.txt", cwd=work)
    git("commit", "-m", "base", cwd=work)
    base = git("rev-parse", "HEAD", cwd=work)
    (work / "example.txt").write_text("reviewed change\n")
    git("commit", "-am", "reviewed", cwd=work)
    head = git("rev-parse", "HEAD", cwd=work)
    git("remote", "add", "origin", str(remote), cwd=work)
    git(
        "push",
        "origin",
        f"{base}:refs/heads/main",
        f"{base}:refs/heads/staging",
        f"{head}:refs/pull/8/head",
        cwd=work,
    )
    original = gate.git_run

    def local_git(directory, *args, **kwargs):
        if args[:3] == ("remote", "add", "origin"):
            args = (*args[:3], str(remote))
        return original(directory, *args, **kwargs)

    monkeypatch.setattr(gate, "git_run", local_git)
    monkeypatch.setattr(gate, "readiness", Mock())
    monkeypatch.setenv("GH_TOKEN", "local-test-placeholder")
    github = Mock(repository=REPO)
    github.pages.return_value = []
    evidence = {**evidence, "head_sha": head, "base_sha": base}
    gate.approve_and_stage(
        github, pr, evidence, {"model": "test", "confidence": 0.99}, []
    )
    assert git("--git-dir", str(remote), "rev-parse", "main") == base
    assert (
        git("--git-dir", str(remote), "show", "staging:example.txt")
        == "reviewed change"
    )
    git("--git-dir", str(remote), "merge-base", "--is-ancestor", head, "staging")
    assert github.api.call_args.kwargs["body"]["commit_id"] == head


def test_scan_respects_explicit_pr_number(monkeypatch):
    github = Mock(repository=REPO)
    github.pages.return_value = [
        {"number": number, "pull_request": {"url": "test"}} for number in (7, 8)
    ]
    github.api.side_effect = [
        {"workflow_runs": []},
        {"workflow_runs": []},
        {"head": {"sha": HEAD}},
    ]
    monkeypatch.setattr(gate, "is_staged", lambda *args: True)
    assert gate.scan(github, False, [], expected_number=8) == [
        {"pr_number": 8, "status": "already_staged"}
    ]
    assert github.api.call_args.args[0] == "pulls/8"


def test_single_decision_preserves_complete_review_and_patch_audit(
    evaluate_ready, monkeypatch, evidence
):
    import hashlib

    diff = "diff --git a/one b/one\n+" + "é" * 25000
    diff += "\ndiff --git a/two b/two\n+" + "🐦" * 15000
    monkeypatch.setattr(gate, "fetch_diff", lambda *args: diff)
    result = gate.evaluate(evaluate_ready, 90)
    gate.evaluate_review.assert_awaited_once()
    request = gate.evaluate_review.await_args.args[0]
    assert request["review"] == evidence["review_text"]
    assert request["automatic_review"] == {"verdict": "PASS", "blocking_findings": 0}
    assert request["checks"] == [{"name": "test", "conclusion": "success"}]
    assert request["verified_facts"]["exact_revision_verified"]
    assert request["verified_facts"]["required_ci_passed"]
    assert len(request["changed_files"]) == 2
    for key in ("diff", "head_sha", "base_sha", "diff_sha256", "diff_manifest"):
        assert key not in request
    assert "é" * 100 not in json.dumps(request, ensure_ascii=False)
    decision = result["decision"]
    assert decision["diff_sha256"] == hashlib.sha256(diff.encode()).hexdigest()
    assert decision["diff_bytes"] == len(diff.encode())
    assert decision["diff_manifest"] == gate.diff_manifest(diff)


def test_oversized_complete_diff_holds_before_decision(evaluate_ready, monkeypatch):
    monkeypatch.setattr(
        gate, "fetch_diff", lambda *args: "é" * (gate.MAX_DIFF // 2 + 1)
    )
    with pytest.raises(gate.Hold, match="budget"):
        gate.evaluate(evaluate_ready, 90)
    gate.evaluate_review.assert_not_awaited()
    gate.approve_and_stage.assert_not_called()


def test_area_request_does_not_mutate_source_state(monkeypatch):
    import asyncio
    import copy

    state = {
        "diff": "diff --git a/test b/test\n+" + "é" * 60000,
        "automatic_review": {"verdict": "PASS", "blocking_findings": 0},
        "checks": [{"name": "test", "conclusion": "success"}],
    }
    initial = copy.deepcopy(state)

    async def decide(request, **kwargs):
        request["automatic_review"]["verdict"] = "FAIL"
        request["checks"].clear()
        return {"approved": True, "model": "test"}

    monkeypatch.setattr(gate, "evaluate_review", decide)
    assert asyncio.run(gate.evaluate_diff(state))["approved"]
    assert state == initial


def action_run(identifier, workflow=10, event="pull_request", **kwargs):
    return {
        "id": identifier,
        "workflow_id": workflow,
        "event": event,
        "head_sha": HEAD,
        "status": "completed",
        "conclusion": "success",
        **kwargs,
    }


def action_check(identifier, run, conclusion="success", **kwargs):
    return {
        "id": identifier,
        "name": "test",
        "status": "completed",
        "conclusion": conclusion,
        "app": {"slug": "github-actions"},
        "details_url": f"https://github.com/{REPO}/actions/runs/{run}/job/1",
        **kwargs,
    }


def test_old_cancelled_run_superseded_by_same_workflow_event_success():
    github = Mock(repository=REPO)
    github.pages.return_value = [action_run(1), action_run(2)]
    current = action_check(20, 2)
    assert gate.current_run_checks(
        github,
        HEAD,
        [
            action_check(10, 1, "cancelled"),
            current,
        ],
    ) == [current]


@pytest.mark.parametrize(
    "other",
    [
        {"workflow": 11},
        {"event": "push"},
    ],
)
def test_different_workflow_or_event_cannot_hide_failure(other):
    github = Mock(repository=REPO)
    github.pages.return_value = [action_run(1, **other), action_run(2)]
    failure = action_check(10, 1, "failure")
    assert failure in gate.current_run_checks(
        github, HEAD, [failure, action_check(20, 2)]
    )


def test_newer_pending_run_blocks_even_before_its_jobs_appear():
    github = Mock(repository=REPO)
    github.pages.return_value = [
        action_run(1),
        action_run(2, status="queued", conclusion=None),
    ]
    result = gate.current_run_checks(github, HEAD, [action_check(10, 1, "cancelled")])
    assert len(result) == 1
    assert result[0]["status"] == "queued" and result[0]["conclusion"] is None


def test_latest_job_attempt_only_within_same_run_and_job_name():
    github = Mock(repository=REPO)
    github.pages.return_value = [action_run(1)]
    newer = action_check(11, 1)
    assert gate.current_run_checks(
        github, HEAD, [action_check(10, 1, "failure"), newer]
    ) == [newer]


def test_unknown_or_non_actions_check_is_preserved():
    github = Mock(repository=REPO)
    github.pages.return_value = [action_run(1), action_run(2)]
    unknown = action_check(1, 99, "failure")
    other_app = action_check(2, 1, "failure", app={"slug": "external-ci"})
    assert gate.current_run_checks(github, HEAD, [unknown, other_app]) == [
        unknown,
        other_app,
    ]


def test_new_workflow_waiting_for_jobs_still_blocks():
    github = Mock(repository=REPO)
    github.pages.return_value = [action_run(1, status="queued", conclusion=None)]
    result = gate.current_run_checks(github, HEAD, [])
    assert len(result) == 1
    assert result[0]["status"] == "queued"


@pytest.mark.parametrize(
    "value", ["0.79", "1.01", "NaN", "inf", "-inf", "true", "", "garbage"]
)
def test_invalid_admin_threshold_holds_before_any_network(
    evaluate_ready, monkeypatch, value
):
    monkeypatch.setenv("DECISION_MERGE_AREA_THRESHOLD", value)
    read = Mock()
    monkeypatch.setattr(gate, "read_evidence", read)
    with pytest.raises(gate.Hold, match="area policy"):
        gate.evaluate(evaluate_ready, 90)
    read.assert_not_called()
    gate.evaluate_review.assert_not_awaited()


def test_admin_area_threshold_is_read_once(evaluate_ready, monkeypatch):
    monkeypatch.setenv("DECISION_MERGE_AREA_THRESHOLD", "0.8")

    async def choose(state, **kwargs):
        assert kwargs["area_threshold"] == 0.8
        monkeypatch.setenv("DECISION_MERGE_AREA_THRESHOLD", "0.99")
        return {"approved": True, "model": "test"}

    gate.evaluate_review.side_effect = choose
    assert gate.evaluate(evaluate_ready, 90)["status"] == "would_stage"
    gate.evaluate_review.assert_awaited_once()


def test_old_confidence_variable_requires_explicit_migration(
    evaluate_ready, monkeypatch
):
    monkeypatch.setenv("DECISION_MERGE_MIN_CONFIDENCE", "0.95")
    read = Mock()
    monkeypatch.setattr(gate, "read_evidence", read)
    with pytest.raises(gate.Hold, match="obsolete"):
        gate.evaluate(evaluate_ready, 90)
    read.assert_not_called()


def test_readable_summary_exposes_area_policy_and_blocker_veto():
    decision = {
        "model": "decision-model",
        "policy_verdict": "approve",
        "area_threshold": 0.8,
        "passed_area_count": 4,
        "required_area_count": 4,
        "blocker_probability": 0.06,
        "areas": {
            "correctness": {"probability": 0.87304, "passed": True, "critical": True},
            "architecture": {"probability": 0.65, "passed": False, "critical": False},
        },
        "reasons": ["Four areas pass and both critical areas pass."],
    }
    summary = gate.readable_summary({"status": "would_stage", "decision": decision})
    assert "87.30%" in summary and "80.00%" in summary and "65.00%" in summary
    assert "6.00%" in summary and "vetoes admission" in summary
    assert "Policy verdict: **approve**" in summary and "decision-model" in summary
    assert "4 / 5" in summary and "Correctness and security must both pass" in summary
    assert "not measured accuracy" in summary
