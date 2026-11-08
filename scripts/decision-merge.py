#!/usr/bin/env python3
"""Consume trusted review evidence and optionally admit its exact SHA to staging."""

import argparse
import asyncio
import io
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from liminal_bridge.review_gate import eligibility, evaluate_review

SOURCES = {
    "opencode": ".github/workflows/opencode.yml",
    "Agent PR Review Dispatch": ".github/workflows/workflow-review-dispatch.yml",
}
GATE_PATH = ".github/workflows/decision-merge.yml"
MAX_ARTIFACT = 512000
MAX_DIFF = 1000000
CONTROL_CHECKS = {
    "review",
    "dispatch-review",
    "check-workflow-changes",
    "request-workflow-review",
    "merge-to-staging",
    "merge-approved-workflow-pr",
}


class Hold(Exception):
    pass


class GitHub:
    def __init__(self, repository):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise Hold("Invalid repository identity")
        self.repository = repository

    def request(self, path, *, method="GET", body=None, raw=False, accept=None):
        command = ["gh", "api", "--hostname", "github.com", "--method", method, path]
        if accept:
            command += ["-H", f"Accept: {accept}"]
        if body is not None:
            command += ["--input", "-"]
        result = subprocess.run(
            command,
            input=json.dumps(body).encode() if body is not None else None,
            capture_output=True,
            timeout=60,
        )
        if result.returncode:
            raise Hold("GitHub request failed; no admission performed")
        if raw:
            return result.stdout
        try:
            return json.loads(result.stdout)
        except (ValueError, UnicodeDecodeError):
            raise Hold("Invalid GitHub response") from None

    def api(self, suffix, **kwargs):
        return self.request(f"repos/{self.repository}/{suffix}", **kwargs)

    def pages(self, suffix, key=None):
        collected = []
        for page in range(1, 21):
            separator = "&" if "?" in suffix else "?"
            data = self.api(f"{suffix}{separator}per_page=100&page={page}")
            items = data.get(key) if key else data
            if not isinstance(items, list):
                raise Hold("Incomplete GitHub evidence")
            collected.extend(items)
            if len(items) < 100:
                return collected
        raise Hold("GitHub evidence exceeds pagination limit")


def artifact_json(archive):
    if len(archive) > MAX_ARTIFACT:
        raise Hold("Review archive exceeds limit")
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            entries = zipped.infolist()
            if len(entries) != 1 or entries[0].filename != "review-evidence.json":
                raise Hold("Unexpected review archive contents")
            if entries[0].file_size > MAX_ARTIFACT:
                raise Hold("Review evidence exceeds limit")
            data = json.loads(zipped.read(entries[0]))
    except (ValueError, OSError, zipfile.BadZipFile, RuntimeError):
        raise Hold("Invalid review archive") from None
    if not isinstance(data, dict):
        raise Hold("Invalid review document")
    return data


def read_evidence(github, run_id):
    run = github.api(f"actions/runs/{run_id}")
    path = SOURCES.get(run.get("name"))
    if (
        not path
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or run.get("repository", {}).get("full_name") != github.repository
        or run.get("path", "").split("@")[0] != path
    ):
        raise Hold("Source is not a successful supported repository review")
    expected_name = f"decision-review-{run_id}-{run['run_attempt']}"
    artifacts = github.pages(f"actions/runs/{run_id}/artifacts", "artifacts")
    matches = [
        item
        for item in artifacts
        if item.get("name") == expected_name and not item.get("expired")
    ]
    if (
        len(matches) != 1
        or matches[0].get("size_in_bytes", MAX_ARTIFACT + 1) > MAX_ARTIFACT
    ):
        raise Hold("A complete review artifact is required")
    archive = github.api(f"actions/artifacts/{matches[0]['id']}/zip", raw=True)
    evidence = artifact_json(archive)
    if (
        evidence.get("run_id") != run_id
        or evidence.get("run_attempt") != run["run_attempt"]
        or evidence.get("workflow_path") != path
        or evidence.get("repository") != github.repository
    ):
        raise Hold("Review artifact provenance mismatch")
    return run, evidence


def verify_workflow(github, run, evidence, pr):
    # A PR may change its workflow YAML. Such a run cannot certify itself.
    path = evidence["workflow_path"]
    trusted = github.api(f"contents/{path}?ref={pr['base']['sha']}")
    if run.get("event") == "pull_request_target":
        # GitHub executes target-event workflow code from the default branch.
        # The run API may nevertheless report the PR head as head_sha. Bind the
        # authenticated target event to this PR/base rather than treating that
        # metadata field as the workflow source revision.
        if (
            pr.get("base", {}).get("ref") != "main"
            or type(pr.get("base", {}).get("repo", {}).get("id")) is not int
            or not any(
                item.get("number") == pr.get("number")
                and item.get("base", {}).get("sha") == pr["base"]["sha"]
                and item.get("base", {}).get("ref") == "main"
                and item.get("base", {}).get("repo", {}).get("id")
                == pr.get("base", {}).get("repo", {}).get("id")
                for item in run.get("pull_requests", [])
                if isinstance(item, dict)
            )
        ):
            raise Hold("Target review is not bound to this PR and base")
        if trusted.get("sha"):
            return
    executed = github.api(f"contents/{path}?ref={run['head_sha']}")
    if trusted.get("sha") and executed.get("sha") == trusted["sha"]:
        return
    # One-time installation explicitly authorized by the repository owner. The
    # admin-owned variable pins the entire audited commit, not PR-supplied text.
    # This exception cannot apply to another PR, revision, actor, or base.
    pin = os.getenv("DECISION_GATE_BOOTSTRAP_SHA", "")
    if (
        re.fullmatch(r"[0-9a-f]{40}", pin)
        and github.repository == "niklas-olsson/keystone-polyphony"
        and pr.get("number") == 86
        and pr.get("head", {}).get("sha") == pin
        and pr.get("head", {}).get("ref") == "feat/lokimetasmith-sync"
        and pr.get("head", {}).get("repo", {}).get("full_name") == github.repository
        and pr.get("base", {}).get("sha") == "8f23c9c7b721ad47ffbf5358a812dac2dba66999"
        and run.get("head_sha") == pin
        and run.get("event") == "pull_request"
        and run.get("actor", {}).get("login") == "niklas-olsson"
        and path == ".github/workflows/opencode.yml"
        and os.getenv("GITHUB_SHA") == pin
        and os.getenv("GITHUB_EVENT_NAME") == "push"
        and os.getenv("GITHUB_ACTOR") == "niklas-olsson"
        and os.getenv("GITHUB_REF") == "refs/heads/feat/lokimetasmith-sync"
        and os.getenv("GITHUB_REPOSITORY") == github.repository
    ):
        return
    raise Hold("Review workflow differs from trusted base; maintainer review required")


def unresolved_threads(github, number):
    owner, name = github.repository.split("/")
    cursor = None
    query = """query($owner:String!,$name:String!,$number:Int!,$cursor:String){
      repository(owner:$owner,name:$name){pullRequest(number:$number){
        reviewThreads(first:100,after:$cursor){nodes{isResolved}
          pageInfo{hasNextPage endCursor}}}}}"""
    for _ in range(20):
        result = github.request(
            "graphql",
            method="POST",
            body={
                "query": query,
                "variables": {
                    "owner": owner,
                    "name": name,
                    "number": number,
                    "cursor": cursor,
                },
            },
        )
        try:
            threads = result["data"]["repository"]["pullRequest"]["reviewThreads"]
            if result.get("errors") or any(
                item["isResolved"] is not True for item in threads["nodes"]
            ):
                return True
            if not threads["pageInfo"]["hasNextPage"]:
                return False
            cursor = threads["pageInfo"]["endCursor"]
        except (KeyError, TypeError):
            raise Hold("Review thread evidence unavailable") from None
    raise Hold("Review threads exceed pagination limit")


def current_run_checks(github, commit, checks):
    """Supersede checks only within one authenticated Actions workflow/event."""
    runs = github.pages(f"actions/runs?head_sha={commit}", "workflow_runs")
    known = {}
    latest = {}
    for run in runs:
        if (
            run.get("head_sha") != commit
            or type(run.get("id")) is not int
            or type(run.get("workflow_id")) is not int
            or not isinstance(run.get("event"), str)
        ):
            continue
        key = (run["workflow_id"], run["event"])
        known[run["id"]] = run
        if key not in latest or run["id"] > latest[key]["id"]:
            latest[key] = run
    matched = []
    untouched = []
    for check in checks:
        match = re.match(
            r"^https://github\.com/"
            + re.escape(github.repository)
            + r"/actions/runs/([0-9]+)(?:/|$)",
            check.get("details_url") or "",
        )
        run = known.get(int(match[1])) if match else None
        if check.get("app", {}).get("slug") != "github-actions" or not run:
            untouched.append(check)
            continue
        key = (run["workflow_id"], run["event"])
        if run["id"] == latest[key]["id"]:
            matched.append((run["id"], check))
    # Re-running jobs keeps the run ID. Retain the latest check ID for each
    # job name within that run, without conflating different workflows/events.
    jobs = {}
    for run_id, check in matched:
        key = (run_id, check.get("name"))
        previous = jobs.get(key)
        if previous is None or check.get("id", 0) > previous.get("id", 0):
            jobs[key] = check
    result = untouched + list(jobs.values())
    for key in latest:
        run = latest[key]
        # A new run may supersede old checks before creating any new jobs.
        # Its unfinished/failed state must still prevent admission. The gate
        # itself is handled by readiness's existing provenance exemption.
        if run.get("path", "").split("@")[0] == GATE_PATH:
            continue
        if run.get("status") != "completed" or run.get("conclusion") not in {
            "success",
            "skipped",
            "neutral",
        }:
            result.append(
                {
                    "name": f"Actions workflow {run['workflow_id']} ({run['event']})",
                    "status": run.get("status"),
                    "conclusion": run.get("conclusion"),
                }
            )
    return result


def readiness(github, number, evidence, required_checks):
    pr = github.api(f"pulls/{number}")
    sha = pr["head"]["sha"]
    # pull_request validation runs on GitHub's synthetic merge commit. Evaluate
    # that current candidate as well as checks attached directly to the head.
    commits = [sha]
    merge_sha = pr.get("merge_commit_sha")
    if (
        isinstance(merge_sha, str)
        and re.fullmatch(r"[0-9a-f]{40}", merge_sha)
        and merge_sha != sha
    ):
        commits.append(merge_sha)
    own_runs = []
    checks = []
    statuses = []
    for commit in commits:
        own_runs.extend(
            github.pages(
                f"actions/workflows/decision-merge.yml/runs?head_sha={commit}",
                "workflow_runs",
            )
        )
        checks.extend(
            current_run_checks(
                github,
                commit,
                github.pages(
                    f"commits/{commit}/check-runs?filter=latest", "check_runs"
                ),
            )
        )
        latest = {}
        for status in github.pages(f"commits/{commit}/statuses"):
            latest.setdefault(status.get("context"), status)
        statuses.extend(latest.values())
    own_urls = {
        f"https://github.com/{github.repository}/actions/runs/{item['id']}/"
        for item in own_runs
    }
    external = []
    for check in checks:
        details = check.get("details_url") or ""
        if (
            check.get("name") == "decision-gate"
            and check.get("app", {}).get("slug") == "github-actions"
            and any(details.startswith(url) for url in own_urls)
        ):
            continue
        # Review success/control-plane bookkeeping is not a successful test.
        # Their failures and pending states still prevent admission.
        if check.get("name") in CONTROL_CHECKS and check.get("conclusion") in {
            "success",
            "skipped",
            "neutral",
        }:
            continue
        external.append(check)
    reviews = github.pages(f"pulls/{number}/reviews")
    threads = unresolved_threads(github, number)
    reasons = eligibility(
        pr,
        evidence,
        external,
        statuses,
        reviews,
        threads,
        required_checks,
    )
    if reasons:
        raise Hold("; ".join(reasons))
    return pr, external


def fetch_diff(github, pr, evidence):
    files = github.pages(f"pulls/{pr['number']}/files")
    if not files or any(not isinstance(item.get("patch"), str) for item in files):
        raise Hold(
            "Complete text diff required; binary or omitted patches need maintainer review"
        )
    if evidence.get("scope") == "workflow" and any(
        not item["filename"].startswith(".github/workflows/") for item in files
    ):
        raise Hold("Workflow-only review cannot approve non-workflow changes")
    raw = github.api(
        f"compare/{evidence['base_sha']}...{evidence['head_sha']}",
        raw=True,
        accept="application/vnd.github.diff",
    )
    if not raw or len(raw) > MAX_DIFF:
        raise Hold("Complete PR diff exceeds decision context budget")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise Hold("PR diff is not text") from None


def diff_manifest(diff):
    """Describe every complete file section for the audit record."""
    sections = re.split(r"(?m)(?=^diff --git )", diff)
    return [
        {
            "header": section.split("\n", 1)[0],
            "bytes": len(section.encode("utf-8")),
            "sha256": hashlib.sha256(section.encode("utf-8")).hexdigest(),
        }
        for section in sections
        if section
    ]


def decision_threshold():
    """Read the area policy before fetching or evaluating evidence."""
    if os.getenv("DECISION_MERGE_MIN_CONFIDENCE"):
        raise Hold(
            "DECISION_MERGE_MIN_CONFIDENCE is obsolete; configure DECISION_MERGE_AREA_THRESHOLD explicitly"
        )
    try:
        value = float(os.getenv("DECISION_MERGE_AREA_THRESHOLD", "0.8"))
    except (TypeError, ValueError):
        raise Hold("Invalid decision area policy; expected 0.8 through 1") from None
    if not math.isfinite(value) or not 0.8 <= value <= 1:
        raise Hold("Invalid decision area policy; expected 0.8 through 1")
    return value


async def evaluate_diff(state, area_threshold=0.8):
    """Classify the complete independent review once; retain patch audit binding."""
    diff = state["diff"]
    raw = diff.encode("utf-8")
    if not raw or len(raw) > MAX_DIFF:
        raise Hold("Complete PR diff exceeds decision context budget")
    manifest = diff_manifest(diff)
    # Patches and crypto identifiers bind the audit record, not decision input.
    # The independent reviewer already examined the complete bound patch.
    request = json.loads(
        json.dumps(
            {
                key: value
                for key, value in state.items()
                if key not in {"diff", "head_sha", "base_sha"}
            }
        )
    )
    request["changed_files"] = []
    for item in manifest:
        try:
            paths = shlex.split(item["header"])
        except ValueError:
            raise Hold("Invalid complete diff file header") from None
        if len(paths) != 4 or paths[:2] != ["diff", "--git"]:
            raise Hold("Invalid complete diff file header")
        request["changed_files"].append(paths[3].removeprefix("b/"))
    decision = await evaluate_review(
        request,
        api_key=os.getenv("OPENROUTER_API_KEY", ""),
        model=os.getenv("DECISION_MERGE_MODEL") or "auto",
        area_threshold=area_threshold,
    )
    return {
        **decision,
        "diff_sha256": hashlib.sha256(raw).hexdigest(),
        "diff_bytes": len(raw),
        "diff_manifest": manifest,
    }


def git_run(directory, *args, env=None):
    result = subprocess.run(
        ["git", *args], cwd=directory, env=env, capture_output=True, timeout=120
    )
    if result.returncode:
        raise Hold("Staging integration failed or raced; no forced push attempted")
    return result.stdout.decode().strip()


def is_staged(github, sha):
    try:
        compared = github.api(f"compare/{sha}...staging")
    except Hold:
        return False
    return compared.get("status") in {"ahead", "identical"}


def approve_and_stage(github, pr, evidence, decision, required_checks):
    number, sha = pr["number"], evidence["head_sha"]
    with tempfile.TemporaryDirectory(prefix="decision-staging-") as directory:
        git_run(directory, "init")
        git_run(
            directory,
            "remote",
            "add",
            "origin",
            f"https://github.com/{github.repository}.git",
        )
        git_run(
            directory,
            "fetch",
            "--no-tags",
            "origin",
            "refs/heads/main:refs/remotes/origin/main",
            f"refs/pull/{number}/head:refs/remotes/origin/pr",
        )
        if git_run(directory, "rev-parse", "refs/remotes/origin/pr") != sha:
            raise Hold("PR changed before staging integration")
        staging = git_run(directory, "ls-remote", "origin", "refs/heads/staging")
        if staging:
            git_run(
                directory,
                "fetch",
                "origin",
                "refs/heads/staging:refs/remotes/origin/staging",
            )
        start = "refs/remotes/origin/staging" if staging else "refs/remotes/origin/main"
        git_run(directory, "checkout", "-b", "staging", start)
        git_run(directory, "config", "user.name", "github-actions[bot]")
        git_run(
            directory,
            "config",
            "user.email",
            "41898282+github-actions[bot]@users.noreply.github.com",
        )
        git_run(directory, "merge", "--no-ff", "--no-edit", sha)
        readiness(github, number, evidence, required_checks)
        approval = {
            "commit_id": sha,
            "event": "APPROVE",
            "body": (
                f"[decision-gate] Accepted reviewed commit {sha} for staging. "
                f"Review evidence run: {evidence['run_id']}. "
                "Main promotion still requires staging tests.\n\n"
                + readable_summary({"status": "accepted", "decision": decision})
            ),
        }
        prior = github.pages(f"pulls/{number}/reviews")
        if not any(
            item.get("user", {}).get("login") == "github-actions[bot]"
            and item.get("state") == "APPROVED"
            and item.get("commit_id") == sha
            and (item.get("body") or "").startswith("[decision-gate]")
            for item in prior
        ):
            github.api(f"pulls/{number}/reviews", method="POST", body=approval)
        # Recheck label, reviews, tests and exact head/base after approval too.
        readiness(github, number, evidence, required_checks)
        push_env = os.environ.copy()
        push_env["GH_TOKEN"] = os.getenv("STAGING_PUSH_TOKEN") or os.environ["GH_TOKEN"]
        git_run(
            directory,
            "-c",
            "credential.helper=!gh auth git-credential",
            "push",
            "origin",
            "HEAD:refs/heads/staging",
            env=push_env,
        )


def evaluate(github, run_id, number=0, dry_run=True, required_checks=()):
    area_threshold = decision_threshold()
    run, evidence = read_evidence(github, run_id)
    actual_number = evidence.get("pr_number")
    if (
        type(actual_number) is not int
        or actual_number <= 0
        or (number and number != actual_number)
    ):
        raise Hold("Review PR number mismatch")
    pr, checks = readiness(github, actual_number, evidence, required_checks)
    verify_workflow(github, run, evidence, pr)
    if is_staged(github, evidence["head_sha"]):
        return {"status": "already_staged", "pr_number": actual_number}
    diff = fetch_diff(github, pr, evidence)
    state = {
        "review": evidence["review_text"],
        "automatic_review": {
            "verdict": evidence["review_verdict"],
            "blocking_findings": evidence["blocking_findings"],
        },
        "review_model": evidence.get("model"),
        "verified_facts": {
            "automatic_review_passed": True,
            "required_ci_passed": True,
            "exact_revision_verified": True,
            "no_unresolved_threads": True,
            "no_change_requests": True,
            "complete_review_scope": True,
        },
        "scope": evidence["scope"],
        "diff": diff,
        "head_sha": evidence["head_sha"],
        "base_sha": evidence["base_sha"],
        "checks": [
            {"name": item["name"], "conclusion": item["conclusion"]} for item in checks
        ],
        "policy": "Admit this reviewed commit to staging only. Main promotion requires separate tests.",
    }
    decision = asyncio.run(evaluate_diff(state, area_threshold))
    result = {
        "pr_number": actual_number,
        "head_sha": evidence["head_sha"],
        "decision": decision,
    }
    if not decision["approved"]:
        return {**result, "status": "held"}
    readiness(github, actual_number, evidence, required_checks)
    if dry_run:
        return {**result, "status": "would_stage"}
    approve_and_stage(github, pr, evidence, decision, required_checks)
    return {**result, "status": "staged"}


def scan(github, dry_run, required_checks, expected_number=0):
    """Retry held PRs after checks finish without another expensive CLI review."""
    issues = github.pages("issues?state=open&labels=decision-merge")
    numbers = [
        item["number"]
        for item in issues
        if item.get("pull_request")
        and (not expected_number or item["number"] == expected_number)
    ][:20]
    runs = []
    for path in SOURCES.values():
        data = github.api(
            f"actions/workflows/{path.rsplit('/', 1)[1]}/runs?status=success&per_page=30"
        )
        runs.extend(data["workflow_runs"])
    runs.sort(key=lambda run: run["id"], reverse=True)
    cache = {}
    results = []
    for number in numbers:
        pr = github.api(f"pulls/{number}")
        if is_staged(github, pr["head"]["sha"]):
            results.append({"pr_number": number, "status": "already_staged"})
            continue
        candidate = None
        for run in runs:
            references = run.get("pull_requests") or []
            if references and number not in [item["number"] for item in references]:
                continue
            if run["id"] not in cache:
                try:
                    cache[run["id"]] = read_evidence(github, run["id"])[1]
                except Hold:
                    cache[run["id"]] = None
            evidence = cache[run["id"]]
            if (
                evidence
                and evidence.get("pr_number") == number
                and evidence.get("head_sha") == pr["head"]["sha"]
                and evidence.get("base_sha") == pr["base"]["sha"]
            ):
                candidate = run["id"]
                break
        try:
            if not candidate:
                raise Hold("No fresh review artifact found in recent successful runs")
            results.append(
                evaluate(github, candidate, number, dry_run, required_checks)
            )
        except Hold as error:
            results.append(
                {"pr_number": number, "status": "held", "reason": str(error)}
            )
    return results


def readable_summary(result):
    """Expose area probabilities and the deterministic admission policy."""

    def cell(value):
        return (
            str(value if value is not None else "unavailable")
            .replace("|", "/")
            .replace("\n", " ")
        )

    def percent(value):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return f"{value * 100:.2f}%"
        return "unavailable"

    lines = ["## Decision staging gate", ""]
    for item in result.get("results", [result]):
        decision = item.get("decision", {})
        lines.extend(
            [
                f"Status: **{cell(item.get('status'))}**. "
                f"Policy verdict: **{cell(decision.get('policy_verdict'))}**. "
                f"Model: **{cell(decision.get('model'))}**.",
                "",
                f"Passing areas: **{cell(decision.get('passed_area_count'))} / 5**; "
                f"required: **{cell(decision.get('required_area_count'))}**. "
                "Correctness and security must both pass.",
                "",
                "| Area | Probability | Required | Passed | Critical |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for name, area in decision.get("areas", {}).items():
            lines.append(
                f"| {cell(name)} | {percent(area.get('probability'))} "
                f"| {percent(decision.get('area_threshold'))} "
                f"| {cell(area.get('passed'))} | {cell(area.get('critical'))} |"
            )
        lines.extend(
            [
                "",
                "Unresolved blocking finding probability: "
                f"**{percent(decision.get('blocker_probability'))}**; "
                "**80.00% or higher vetoes admission**.",
                "",
            ]
        )
        for reason in decision.get("reasons", []):
            lines.append(f"- {cell(reason)}")
        if item.get("reason"):
            lines.append(f"- {cell(item['reason'])}")
        lines.append("")
    lines.extend(
        [
            "Probabilities express model classifications, not measured accuracy. "
            "CI, independent reviewer PASS, freshness, and unresolved-thread checks remain mandatory.",
            "",
        ]
    )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=int, default=0)
    parser.add_argument("--pr-number", type=int, default=0)
    parser.add_argument(
        "--scan",
        action="store_true",
        help="Recheck opted-in open PRs using recent review artifacts",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Approve and push staging; default is dry run",
    )
    args = parser.parse_args()
    try:
        github = GitHub(os.environ.get("GITHUB_REPOSITORY", ""))
        required = [
            name.strip()
            for name in os.getenv("DECISION_MERGE_REQUIRED_CHECKS", "").split(",")
            if name.strip()
        ]
        if args.scan:
            result = {"results": scan(github, not args.apply, required, args.pr_number)}
        elif args.run_id > 0:
            result = evaluate(
                github, args.run_id, args.pr_number, not args.apply, required
            )
        else:
            raise Hold("A positive review run ID or --scan is required")
    except (Hold, KeyError, TypeError, ValueError, subprocess.TimeoutExpired) as error:
        # Never print provider bodies, raw review content, or subprocess stderr.
        reason = (
            str(error)
            if isinstance(error, Hold)
            else "Incomplete or invalid gate evidence"
        )
        result = {"status": "held", "reason": reason}
    Path("decision-result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as summary:
            summary.write(
                readable_summary(result)
                + "\n```json\n"
                + json.dumps(result, indent=2)
                + "\n```\n"
            )


if __name__ == "__main__":
    main()
