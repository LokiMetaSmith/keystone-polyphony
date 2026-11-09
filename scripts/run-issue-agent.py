#!/usr/bin/env python3
"""Run one issue-solving agent with explicit provider credentials and bounded time.

Coding invocations are never automatically retried: a failed run may have made
partial changes. Prompt files and CLI state belong outside the Git checkout.
"""

import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile

DEFAULT_MODEL = "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"
PROVIDER_KEYS = {
    "openrouter": "OPENROUTER_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GEMINI_API_KEY",
    "grok": "GROK_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openai": "OPENAI_API_KEY",
}


class AgentConfigurationError(ValueError):
    """A diagnostic assembled only from fixed configuration field names."""


def configuration(environment):
    cli = environment.get("AGENT_CLI", "opencode")
    name = Path(cli).name.lower()
    model = environment.get("AGENT_MODEL", "").strip()
    if name == "opencode" and not model:
        model = DEFAULT_MODEL
    provider = {"claude": "anthropic", "openclaw": "anthropic", "jules": "google"}.get(
        name, "openrouter"
    )
    if "/" in model:
        provider = model.split("/", 1)[0]
    if provider not in PROVIDER_KEYS:
        raise AgentConfigurationError(
            "AGENT_MODEL must use a supported provider prefix (for example openrouter/...)."
        )
    key_name = PROVIDER_KEYS[provider]
    key = (
        environment.get(key_name, "").strip()
        or environment.get("AGENT_API_KEY", "").strip()
    )
    if not key:
        raise AgentConfigurationError(
            f"Missing {key_name} Actions secret (or legacy AGENT_API_KEY)."
        )
    if not shutil.which(cli):
        raise AgentConfigurationError("AGENT_CLI executable is not installed.")
    child_env = {
        k: v
        for k, v in environment.items()
        if k not in {*PROVIDER_KEYS.values(), "AGENT_API_KEY", "OPENAI_API_BASE"}
    }
    child_env[key_name] = key
    child_env["AGENT_API_KEY"] = key
    command = [cli]
    if name == "opencode":
        command += ["run", "--format", "json"]
        config = json.loads(environment.get("OPENCODE_CONFIG_CONTENT", "{}"))
        config["permission"] = "allow"
        child_env["OPENCODE_CONFIG_CONTENT"] = json.dumps(config)
        child_env["OPENCODE_DISABLE_AUTOUPDATE"] = "true"
    command += shlex.split(environment.get("AGENT_CLI_FLAGS", ""))
    if name == "openclaw":
        command += ["--yolo"]
    elif name == "claude":
        command += ["--print"]
    if model:
        command += ["--model", model]
    # OpenCode appends stdin to this short positional instruction. Never put the
    # full issue body in argv (Linux has a per-argument size limit).
    if name == "opencode":
        command += [
            "Implement the supplied issue in this checkout; do not commit, push, or open a PR."
        ]
    return command, child_env, name, model, provider


def run(prompt, environment):
    command, child_env, name, model, provider = configuration(environment)
    if name not in {"opencode", "claude"}:
        # Preserve the existing custom-agent prompt flag contract. Native
        # OpenCode/Claude use stdin; custom CLIs retain their argv size limits.
        command += ["--prompt", Path(prompt).read_text()]
    timeout = int(environment.get("AGENT_TIMEOUT_SECONDS", "600"))
    if not 1 <= timeout <= 3600:
        raise AgentConfigurationError(
            "AGENT_TIMEOUT_SECONDS must be between 1 and 3600."
        )
    print(
        f"Running {name}; provider={provider}; model={model or 'CLI default'}",
        flush=True,
    )
    with tempfile.TemporaryDirectory(prefix="issue-agent-") as state:
        if name == "opencode":
            # HOME alone does not override explicit XDG/OpenCode paths. Isolate
            # all CLI state to avoid concurrent first-run migration collisions.
            child_env.update(
                HOME=state,
                XDG_CONFIG_HOME=state + "/config",
                XDG_DATA_HOME=state + "/data",
                XDG_CACHE_HOME=state + "/cache",
                XDG_STATE_HOME=state + "/state",
            )
            child_env.pop("OPENCODE_DB", None)
        with open(prompt, "rb") as source:
            process = subprocess.Popen(
                command,
                stdin=source,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=child_env,
                start_new_session=True,
            )
            try:
                output, errors = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.communicate()
                print(
                    "Agent execution timed out; partial changes were not published.",
                    file=sys.stderr,
                )
                return 124
    if process.returncode:
        print(
            f"Agent process failed with exit code {process.returncode}; partial changes were not published.",
            file=sys.stderr,
        )
        return process.returncode if process.returncode > 0 else 1
    if name == "opencode":
        text = []
        completed = False
        for line in output.decode("utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except ValueError:
                print("Invalid OpenCode event output.", file=sys.stderr)
                return 1
            if not isinstance(event, dict) or event.get("type") == "error":
                print(
                    "OpenCode reported an invocation/provider error.", file=sys.stderr
                )
                return 1
            part = event.get("part", {})
            if isinstance(part, dict):
                if event.get("type") == "text" and isinstance(part.get("text"), str):
                    text.append(part["text"])
                if event.get("type") == "step_finish" and part.get("reason") == "stop":
                    completed = True
        if not completed or not any(t.strip() for t in text):
            print(
                "OpenCode did not return a completed assistant response.",
                file=sys.stderr,
            )
            return 1
    print(
        "Agent invocation completed; repository changes still require validation and review."
    )
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        if args.check:
            configuration(os.environ)
            print("Agent configuration is valid; credentials were not printed.")
            return 0
        return run(args.prompt, os.environ)
    except AgentConfigurationError as error:
        print(str(error), file=sys.stderr)
        return 2
    except (ValueError, OSError, TypeError):
        # Configuration parse errors may contain caller input; do not dump it.
        print(
            "Agent configuration failed. Check the selected CLI/model and its provider Actions secret.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
