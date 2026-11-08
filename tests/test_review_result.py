"""Automatic approval needs an explicit, final, unambiguous reviewer verdict."""

import pytest

from liminal_bridge.review_result import parse_review_result, review_passed

PASS = 'REVIEW_RESULT: {"verdict":"PASS","blocking_findings":0}'


@pytest.mark.parametrize(
    "prefix",
    [
        "",
        "## Analysis\nLooks good.\n",
        "```\nexample\n```\n",
        "~~~text\nexample\n~~~\n",
    ],
)
def test_pass_is_explicit_and_final(prefix):
    text = prefix + PASS + "\n\n"
    assert parse_review_result(text) == {"verdict": "PASS", "blocking_findings": 0}
    assert review_passed(text)


def test_fail_is_typed_but_never_passes():
    text = 'REVIEW_RESULT: {"verdict":"FAIL","blocking_findings":2}'
    assert parse_review_result(text) == {"verdict": "FAIL", "blocking_findings": 2}
    assert not review_passed(text)


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        "## Recommendation\nGo. No blocking findings.",
        " " + PASS,
        "\t" + PASS,
        "> " + PASS,
        "- " + PASS,
        PASS + " ",
        PASS + "\nLater output",
        PASS + "\n" + PASS,
        'REVIEW_RESULT: {"verdict":"FAIL","blocking_findings":1}\n' + PASS,
        "Example REVIEW_RESULT: format\n" + PASS,
        "```json\n" + PASS,
        "~~~\n" + PASS,
        "````\n```\n" + PASS,
        "```\n" + PASS + "\n```",
        "REVIEW_RESULT: null",
        "REVIEW_RESULT: []",
        "REVIEW_RESULT: {}",
        'REVIEW_RESULT: {"verdict":"pass","blocking_findings":0}',
        'REVIEW_RESULT: {"verdict":"APPROVE","blocking_findings":0}',
        'REVIEW_RESULT: {"verdict":["PASS"],"blocking_findings":0}',
        'REVIEW_RESULT: {"verdict":"PASS","blocking_findings":true}',
        'REVIEW_RESULT: {"verdict":"PASS","blocking_findings":0.0}',
        'REVIEW_RESULT: {"verdict":"FAIL","blocking_findings":-1}',
        'REVIEW_RESULT: {"verdict":"PASS","blocking_findings":1}',
        'REVIEW_RESULT: {"verdict":"PASS","blocking_findings":"0"}',
        'REVIEW_RESULT: {"verdict":"PASS","blocking_findings":0,"note":"safe"}',
        'REVIEW_RESULT: {"verdict":"FAIL","verdict":"PASS","blocking_findings":0}',
        'REVIEW_RESULT: {"verdict":"PASS","blocking_findings":1,"blocking_findings":0}',
        PASS + " trailing prose",
    ],
)
def test_missing_malformed_or_ambiguous_verdict_cannot_pass(text):
    assert parse_review_result(text) is None
    assert not review_passed(text)
