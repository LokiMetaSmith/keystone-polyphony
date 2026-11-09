#!/usr/bin/env python3
"""Bounded OpenCode/OpenRouter trial in a disposable Git repo (no repo edits).

Loads only OPENROUTER_API_KEY from .env without executing it. Uses the model
explicitly requested by --model; default matches the repository CLI reviewer.
Raw logs and credentials remain private in the temporary directory.
"""

import argparse
import asyncio
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiohttp import web
from src.liminal_bridge.coordinator import Coordinator, Conflict
from src.liminal_bridge.coordinator_service import CoordinatorClient, create_app
from src.liminal_bridge.worktree_adapter import GitWorktreeAdapter
from src.liminal_bridge.worker import Worker


def load_key():
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key and Path(".env").exists():
        for line in Path(".env").read_text().splitlines():
            name, sep, value = line.partition("=")
            if sep and name.strip() == "OPENROUTER_API_KEY":
                key = value.strip().strip('"').strip("'")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is required")
    return key


async def trial(args):
    key = load_key()
    executable = shutil.which("opencode")
    if not executable:
        raise RuntimeError("opencode is required")
    with tempfile.TemporaryDirectory(prefix="polyphony-trial-") as temporary:
        root = Path(temporary)
        repo = root / "repo"
        repo.mkdir()
        for command in (
            ["init", "-q"],
            ["config", "user.name", "Trial"],
            ["config", "user.email", "trial@example.invalid"],
        ):
            subprocess.run(["git", "-C", str(repo), *command], check=True)
        (repo / "README.md").write_text("Disposable coordination trial.\n")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-qm", "baseline"], check=True
        )
        store = Coordinator(root / "authority.db")
        adapter = GitWorktreeAdapter(repo, root / "worktrees")
        tokens = {
            name: secrets.token_hex(32)
            for name in ["alice", "bob", "reviewer", "owner"]
        }
        credentials = {
            token: {
                "identity": name,
                "role": "worker" if name in ("alice", "bob") else name,
            }
            for name, token in tokens.items()
        }
        tasks = []
        for name in ("alpha", "beta"):
            tasks.append(
                store.enroll(
                    name,
                    f"Create exactly one file named {name}.txt containing the single line {name} complete. Do not change other files. Do not commit. Use the file editing tools, then finish.",
                    ["file-check"],
                    reviewers=["reviewer"],
                    max_attempts=1,
                    budget_seconds=args.seconds,
                )
            )
        # One busy protected resource; neither worker should spend a call on it.
        holder = store.enroll("holder", "hold", ["tests"], resource="shared")
        attempt = store.start_attempt(holder["id"], "holder", [], args.seconds, "hold")
        store.acquire("shared", attempt["id"], "holder", 0, args.seconds)
        blocked = store.enroll("busy", "must wait", ["tests"], resource="shared")
        home = root / "home"
        home.mkdir()
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(home),
            "OPENROUTER_API_KEY": key,
            "OPENCODE_DISABLE_AUTOUPDATE": "true",
            "OPENCODE_CONFIG_CONTENT": json.dumps(
                {
                    "$schema": "https://opencode.ai/config.json",
                    "permission": "allow",
                    "provider": {
                        "openrouter": {
                            "options": {"apiKey": "{env:OPENROUTER_API_KEY}"}
                        }
                    },
                }
            ),
        }
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
            if name in os.environ:
                env[name] = os.environ[name]
        execution = {
            "base": "HEAD",
            "isolated_home": True,
            "command": [
                executable,
                "run",
                "--pure",
                "--format",
                "json",
                "-m",
                args.model,
            ],
            "env": env,
        }
        runner = web.AppRunner(create_app(store, credentials, adapter, execution))
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        url = "http://127.0.0.1:" + str(site._server.sockets[0].getsockname()[1])
        clients = {
            name: CoordinatorClient(url, token) for name, token in tokens.items()
        }
        workers = [
            Worker(clients[name], name, seconds=args.seconds)
            for name in ("alice", "bob")
        ]
        began = time.monotonic()
        try:
            for worker in workers:
                assert await worker.tick() == "started"
            deadline = time.monotonic() + args.seconds + 20
            while time.monotonic() < deadline:
                if len(store.snapshot()["candidate"]) == 2:
                    break
                await asyncio.sleep(0.1)
            snapshot = store.snapshot()
            assert (
                len(snapshot["candidate"]) == 2
            ), "workers did not preserve candidates within execution limit"
            incorrect_acceptances = 0
            for candidate in snapshot["candidate"]:
                try:
                    await clients["owner"].call("accept", candidate_id=candidate["id"])
                    incorrect_acceptances += 1
                except Conflict:
                    pass
                task = next(t for t in tasks if t["id"] == candidate["task"])
                name = task["title"]
                patch = store.artifact(candidate["patch"])
                expected = f"{name} complete\n"
                changed_files = subprocess.check_output(
                    [
                        "git",
                        "-C",
                        str(adapter._path(candidate["attempt"])),
                        "diff",
                        "--cached",
                        "--name-only",
                    ],
                    text=True,
                ).splitlines()
                assert changed_files == [f"{name}.txt"]
                content = (
                    adapter._path(candidate["attempt"]) / f"{name}.txt"
                ).read_text()
                assert (
                    content.splitlines() == expected.splitlines()
                    and f"+{name} complete" in patch
                ), "model did not produce expected artifact"
                await clients["reviewer"].call(
                    "evidence",
                    candidate_id=candidate["id"],
                    check="file-check",
                    passed=True,
                    input_revision=1,
                )
                packet = await clients["owner"].call(
                    "accept", candidate_id=candidate["id"]
                )
                assert not packet["release_authorized"]
            assert (
                next(t for t in snapshot["task"] if t["id"] == blocked["id"])[
                    "attempts"
                ]
                == 0
            )
            assert incorrect_acceptances == 0
            for database_file in root.glob("authority.db*"):
                assert key.encode() not in database_file.read_bytes()
            reopened = Coordinator(store.path)
            assert len(reopened.snapshot()["candidate"]) == 2
            print(
                json.dumps(
                    {
                        "passed": True,
                        "workers": 2,
                        "model": args.model,
                        "conductor": "absent",
                        "preserved_candidates": 2,
                        "busy_resource_model_calls": 0,
                        "incorrect_acceptances": incorrect_acceptances,
                        "elapsed_seconds": round(time.monotonic() - began, 2),
                        "cost": None,
                        "release_authorized": False,
                    },
                    indent=2,
                )
            )
        except Exception as exc:
            # Private diagnostic output is opt-in and never a public record.
            if args.failure_logs:
                log_root = Path(args.failure_logs)
                log_root.mkdir(parents=True, exist_ok=True, mode=0o700)
                for log in adapter.root.glob("*.log"):
                    target = log_root / log.name
                    target.write_bytes(log.read_bytes())
                    target.chmod(0o600)
            # Do not print raw provider logs or errors, which could echo inputs.
            print(
                json.dumps(
                    {
                        "passed": False,
                        "failure_type": type(exc).__name__,
                        "model": args.model,
                    }
                )
            )
            for aid in list(adapter.running):
                result = await adapter.cancel(aid)
                store.observe(aid, result["state"], result["termination_confirmed"])
            raise RuntimeError(
                "live trial failed; credentials and provider logs were not exported"
            ) from None
        finally:
            await runner.cleanup()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model", default="openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"
    )
    parser.add_argument("--seconds", type=float, default=120)
    parser.add_argument(
        "--failure-logs", help="private local directory for failed provider logs"
    )
    args = parser.parse_args()
    asyncio.run(trial(args))


if __name__ == "__main__":
    main()
