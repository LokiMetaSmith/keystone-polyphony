#!/usr/bin/env python3
"""Run a review with bounded, free-model provider failover.

Only provider/invocation failures advance to another candidate. A completed review,
including a FAIL verdict, is returned unchanged for the independent admission gate.
"""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from liminal_bridge.model_picker import get_model_candidates  # noqa: E402

ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def decode_events(output):
    """Extract assistant text and top-level errors from OpenCode JSON events.

    Tool failures are deliberately not provider failures: the model can recover
    from an unsuccessful file lookup and still complete an accurate review.
    """
    text = []
    errors = []
    for line in output.splitlines():
        line = ANSI.sub("", line).strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            # Keep diagnostics separate from authoritative assistant output.
            errors.append("Invalid OpenCode JSON event")
            continue
        if not isinstance(event, dict):
            errors.append("Invalid OpenCode JSON event")
        elif event.get("type") == "error":
            errors.append("OpenCode provider error")
        elif event.get("type") == "text":
            part = event.get("part")
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                text.append(part["text"])
    return "\n".join(text), errors


def run(args, candidates=None):
    candidates = candidates or get_model_candidates("review")
    if not args.model_flag:
        raise ValueError("Automatic model selection requires a model flag")
    command = list(args.command)
    if command and command[0] == "--":
        command.pop(0)
    try:
        position = command.index(args.model_flag) + 1
        command[position]
    except (ValueError, IndexError) as error:
        raise ValueError(
            "Review command must contain its model flag and value"
        ) from error
    if args.json_events:
        command.extend(["--format", "json"])
    last_code = 1
    for raw_model in candidates[:3]:
        model = "openrouter/" + raw_model.removeprefix("openrouter/")
        command[position] = model
        Path(args.model_output).write_text(model + "\n")
        print(f"Trying review model: {model}", file=sys.stderr, flush=True)
        try:
            with (
                open(args.stdin_file, "rb")
                if args.stdin_file
                else open("/dev/null", "rb")
            ) as prompt:
                result = subprocess.run(
                    command,
                    stdin=prompt,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=args.timeout,
                    check=False,
                )
        except subprocess.TimeoutExpired:
            print(
                "Review model invocation timed out; trying next candidate",
                file=sys.stderr,
            )
            last_code = 124
            continue
        output = result.stdout.decode("utf-8", errors="replace")
        errors = []
        if args.json_events:
            output, errors = decode_events(output)
            if not output.strip():
                errors.append("No assistant review text returned")
        # Never shop for an approving model after a completed review. Even when
        # the process exits unsuccessfully, a structured verdict ends failover.
        completed_verdict = "REVIEW_RESULT:" in output
        failed = result.returncode != 0 or bool(errors)
        if not failed or completed_verdict:
            print(output, end="" if output.endswith("\n") else "\n")
            return (result.returncode or 1) if failed else 0
        last_code = result.returncode or 1
        print(
            "Review provider/invocation failed; trying next candidate", file=sys.stderr
        )
    print("All ranked free review models failed", file=sys.stderr)
    return last_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stdin-file")
    parser.add_argument("--model-output", required=True)
    parser.add_argument("--model-flag", default="--model")
    parser.add_argument("--json-events", action="store_true")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        return run(args)
    except (ValueError, OSError, RuntimeError) as error:
        print(f"Free review selection failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
