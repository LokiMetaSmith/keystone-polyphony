"""Regression checks for the historic unauthorized root npm install hook."""

import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.check_root_install_hooks import check_root

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_root_install_hooks.py"


def test_no_root_manifest_is_approved(tmp_path):
    assert check_root(tmp_path)
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path)],
        check=False,
        capture_output=True,
    )
    assert completed.returncode == 0


@pytest.mark.parametrize(
    "manifest",
    [
        {"name": "innocent", "scripts": {}},
        {"name": "unapproved", "scripts": {"preinstall": "echo unsafe"}},
        {"name": "unapproved", "scripts": {"prepare": "echo unsafe"}},
    ],
)
def test_root_manifest_is_rejected_even_if_hook_is_disguised(tmp_path, manifest):
    (tmp_path / "package.json").write_text(json.dumps(manifest))
    assert not check_root(tmp_path)


def test_dangling_root_manifest_symlink_is_rejected(tmp_path):
    (tmp_path / "package.json").symlink_to("missing-package.json")
    assert not check_root(tmp_path)


def test_nested_manifests_do_not_trigger_false_alarm(tmp_path):
    sidecar = tmp_path / "src" / "liminal_bridge" / "sidecar"
    sidecar.mkdir(parents=True)
    (sidecar / "package.json").write_text('{"name": "allowed-child-package"}')
    assert check_root(tmp_path)
