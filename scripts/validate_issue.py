#!/usr/bin/env python3
"""Fail closed when an agent issue lacks an actionable review contract."""

import argparse
from pathlib import Path
import re
import sys


def validate(content: str) -> list[str]:
    problems = []
    if not re.search(r"(?m)^# [^\n#].+", content):
        problems.append("a level-one issue title")
    headings = re.findall(r"(?im)^#{2,4}\s+(.+?)\s*$", content)
    normalized = {re.sub(r"[^a-z0-9]", "", h.lower()) for h in headings}
    required = {
        "Human Interaction Story": {"humaninteractionstory", "userstory"},
        "Acceptance Criteria": {"acceptancecriteria"},
        "Prerequisites": {"prerequisites", "dependencies"},
        "Scope": {"scope", "proposedscope", "scopeandnongoals"},
    }
    for label, accepted in required.items():
        if not (normalized & accepted):
            problems.append(label)

    fence = "(?:" + re.escape(chr(96) * 3) + "|~{3})"
    blocks = re.findall(
        rf"(?ims)^{fence}(?:gherkin|feature)\s*\n(.*?)^{fence}\s*$", content
    )
    if not any(
        re.search(r"(?m)^\s*Feature:\s*\S", block)
        and re.search(r"(?m)^\s*Scenario(?: Outline)?:\s*\S", block)
        and re.search(r"(?m)^\s*(?:Given|When|Then)\s+\S", block)
        for block in blocks
    ):
        problems.append("a fenced Gherkin feature and scenario with steps")

    if not re.search(r"(?m)^\s*(?:[-*]|\d+\.)\s+.+", content):
        problems.append("specific requirements or acceptance items")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    try:
        content = args.file.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        print(f"Cannot read issue file: {exc}", file=sys.stderr)
        return 1
    problems = validate(content)
    if problems:
        print(
            "Issue is not publishable. Missing: " + ", ".join(problems),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
