#!/usr/bin/env python3
"""Reject an unreviewed root Node manifest before any npm lifecycle can run.

Only the separate, reviewed Node package manifests under scripts/ and
src/liminal_bridge/sidecar/ are needed by this repository.
"""

import argparse
from pathlib import Path
import sys


def check_root(root: Path) -> bool:
    manifest = root / "package.json"
    # Also reject dangling symlinks, which can otherwise evade Path.exists().
    if manifest.is_symlink() or manifest.exists():
        print(
            "[ERROR] Unexpected root package.json. "
            "Do not install root npm dependencies. "
            "Review any manifest change before allowing a lifecycle script.",
            file=sys.stderr,
        )
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    return 0 if check_root(args.root) else 1


if __name__ == "__main__":
    raise SystemExit(main())
