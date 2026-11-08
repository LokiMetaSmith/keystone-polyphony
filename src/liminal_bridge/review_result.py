"""Parse an explicit review verdict without trusting prose or CLI success."""

import json
import re

MARKER = "REVIEW_RESULT:"


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate review result field")
        result[key] = value
    return result


def parse_review_result(text):
    """Return a strictly typed final verdict, or None for ambiguous output.

    The one marker must be on the final nonempty line, outside Markdown code
    fences, and have no indentation, quotation prefix, or surrounding prose.
    A well-formed FAIL is returned for inspection but never passes admission.
    """
    if not isinstance(text, str) or text.count(MARKER) != 1:
        return None
    lines = text.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return None
    final = lines[-1]
    if not final.startswith(MARKER + " ") or final != final.rstrip():
        return None
    fence = None
    for line in lines[:-1]:
        match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if not match:
            continue
        delimiter, suffix = match.groups()
        if fence is None:
            fence = delimiter
        elif (
            delimiter[0] == fence[0]
            and len(delimiter) >= len(fence)
            and not suffix.strip()
        ):
            fence = None
    if fence is not None:
        return None
    try:
        result = json.loads(final[len(MARKER) + 1 :], object_pairs_hook=_unique_object)
    except (ValueError, TypeError):
        return None
    if not isinstance(result, dict) or set(result) != {"verdict", "blocking_findings"}:
        return None
    if result["verdict"] not in ("PASS", "FAIL"):
        return None
    count = result["blocking_findings"]
    if type(count) is not int or count < 0:
        return None
    if result["verdict"] == "PASS" and count != 0:
        return None
    return result


def review_passed(text):
    """Require the automatic reviewer itself to issue an unambiguous PASS."""
    result = parse_review_result(text)
    return result is not None and result["verdict"] == "PASS"
