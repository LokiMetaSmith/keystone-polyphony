"""Executable script modes are a collaboration protocol precondition."""

import os
from pathlib import Path
import stat

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "script",
    [
        "scripts/lint.sh",
        "scripts/run-tests.sh",
        "scripts/triage-dispatch.sh",
        "scripts/refine_issue.py",
    ],
)
def test_directly_invoked_repo_scripts_remain_executable(script):
    if os.name != "posix":
        pytest.skip("POSIX executable mode is not reliable on this platform")
    mode = (ROOT / script).stat().st_mode
    assert mode & stat.S_IXUSR, f"{script} lost its executable bit"
