#!/usr/bin/env python3
"""Offline coordination demo: scripted roles, production mesh and Pulse logic.

Run from the repository with its Python dependencies installed. By default no
external service is contacted. --live adds one real decision-model request.
This demonstrates coordination of an implementation task; the role nodes do
not generate or implement code.
"""

import asyncio
import argparse
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from liminal_bridge.decisions import DecisionAdvisor
from liminal_bridge.mesh import LiminalMesh
from liminal_bridge.pulse import Pulse
from liminal_bridge.storage import SQLiteStorageProvider


class Loopback:
    """Replace only sidecar I/O; preserve signing, encryption and receive checks."""

    def __init__(self, nodes):
        self.nodes = nodes
        self.deliveries = 0
        for node in nodes:
            node.peers = {peer.node_id for peer in nodes if peer is not node}

            async def send(message_type, envelope, sender=node):
                if message_type != "broadcast":
                    raise RuntimeError(
                        f"Unexpected transport operation: {message_type}"
                    )
                if not {"e", "s", "p"} <= envelope.keys():
                    raise RuntimeError("Unsigned or unencrypted envelope")
                for peer in self.nodes:
                    if peer is not sender:
                        # Copy as a real JSON wire transport would.
                        await peer._handle_message(
                            {
                                "type": "message",
                                "peer_id": sender.node_id,
                                "payload": json.loads(json.dumps(envelope)),
                            }
                        )
                        self.deliveries += 1

            node._send_to_sidecar = send


class FixtureArchitect:
    """Explicit fixed plan, never an LLM pretending to perform implementation."""

    def __init__(self):
        self.calls = 0

    async def consult(self, state):
        self.calls += 1
        return json.dumps(
            {
                "objective": "Implement optional decision-model advice at the Pulse boundary",
                "steps": [
                    "Default off",
                    "Validate typed actions",
                    "Fallback to architect",
                ],
                "commands": [],
            }
        )


class FixtureAdvisor:
    """Already-typed advisor results; does not test the HTTP response parser."""

    def __init__(self, action, status):
        self.result = {"action": action, "status": status}

    async def evaluate(self, state):
        return dict(self.result)


async def chat(node, content):
    await node.update_set(
        "chat:architecture",
        json.dumps(
            {
                "sender": node.node_id,
                "timestamp": time.time(),
                "content": content,
            }
        ),
    )


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


async def run_demo(live=False):
    if live and not os.getenv("OPENROUTER_API_KEY", "").strip():
        raise RuntimeError("--live requires OPENROUTER_API_KEY")
    print("Roles: three scripted nodes (planner, implementer, reviewer).")
    print("Transport: in-process loopback; production encrypted, signed mesh messages.")
    print(
        "Models: scripted Architect and decision fixtures; no autonomous code generation."
    )
    print(
        "Live Decisions API request: "
        + ("enabled (one request)." if live else "disabled.")
    )
    nodes = []
    with tempfile.TemporaryDirectory(prefix="decision-ensemble-") as directory:
        try:
            swarm_key = secrets.token_urlsafe(32)
            for role in ("planner", "implementer", "reviewer"):
                root = Path(directory) / role
                root.mkdir()
                nodes.append(
                    LiminalMesh(
                        swarm_key,
                        storage_provider=SQLiteStorageProvider(str(root / "mesh.db")),
                        identity_path=str(root / "identity.pem"),
                        snapshot_path=str(root / "snapshot.json"),
                    )
                )
            planner, implementer, reviewer = nodes
            transport = Loopback(nodes)
            await implementer.advertise_capabilities(["python"])
            await chat(
                planner,
                "Proposal: optional decision models advise Pulse; default off, "
                "typed actions only, refusal/error falls back to the architect.",
            )
            task = {
                "id": "optional-decision-models",
                "status": "todo",
                "description": "Implement optional decision-model advice in Pulse",
                "required": ["python"],
                "priority": "high",
            }
            await planner.update_set("swarm_backlog", json.dumps(task))
            architect = FixtureArchitect()

            # Production adapter's explicit disabled configuration preserves legacy behavior.
            pulse = Pulse(
                planner, architect, decision_advisor=DecisionAdvisor(enabled=False)
            )
            await pulse.trigger("demo_disabled")
            require(
                architect.calls == 1, "Disabled advisor did not consult the architect"
            )
            print("PASS disabled production advisor: legacy architect path.")

            picked = await implementer.autonomously_pick_task()
            require(
                picked is not None and picked["id"] == task["id"],
                "Capability-based task claim failed",
            )
            print("PASS python-capable implementer claimed task and acquired baton.")

            pulse = Pulse(
                planner, architect, decision_advisor=FixtureAdvisor("continue", "ok")
            )
            await pulse.trigger("demo_continue")
            require(
                architect.calls == 1,
                "Continue fixture unexpectedly consulted architect",
            )
            print(
                "PASS typed continue fixture: current plan retained; architect skipped."
            )

            pulse = Pulse(
                planner,
                architect,
                decision_advisor=FixtureAdvisor("consult_architect", "refused"),
            )
            await pulse.trigger("demo_refusal")
            require(
                architect.calls == 2, "Refusal fixture did not fall back to architect"
            )
            print("PASS refusal fixture: architect fallback.")

            await chat(
                implementer,
                "Scripted task result: exercised disabled, continue, "
                "and refusal paths in production Pulse. No source code generated.",
            )
            old_entries = list(implementer.get_kv("swarm_backlog"))
            for entry in old_entries:
                if json.loads(entry).get("id") == task["id"]:
                    await implementer.update_set("swarm_backlog", entry, remove=True)
            picked["status"] = "done"
            picked["result"] = (
                "Scripted coordination and Pulse behavior demonstration passed"
            )
            await implementer.update_set("swarm_backlog", json.dumps(picked))
            await implementer.release_baton(f"task:{task['id']}")
            await chat(
                reviewer,
                "Review: three Pulse paths passed; task completion and "
                "baton release checked. This fixture demo is not an implementation review.",
            )
            # Baton audit records use create_task; let those writes finish before cleanup.
            await asyncio.sleep(0)
            expected_plan = planner.get_kv("master_plan")
            expected_chat = planner.get_kv("chat:architecture")
            for node in nodes:
                tasks = [json.loads(entry) for entry in node.get_kv("swarm_backlog")]
                require(
                    len(tasks) == 1 and tasks[0]["status"] == "done",
                    "Task CRDT did not converge to a single done entry",
                )
                require(
                    node.get_kv("master_plan") == expected_plan,
                    "Master plan did not converge",
                )
                require(
                    node.get_kv("chat:architecture") == expected_chat,
                    "Architecture chat did not converge",
                )
                require(not node.batons, "Task baton was not released everywhere")
            print(
                f"PASS all 3 nodes agree: task done, master_plan, review chat, no baton; "
                f"{transport.deliveries} signed/encrypted deliveries."
            )
            if live:
                pulse = Pulse(
                    planner, architect, decision_advisor=DecisionAdvisor(enabled=True)
                )
                await pulse.trigger("routine_check")
                result = pulse.last_decision
                # Print only the adapter's validated summary, never raw provider bodies.
                print("Live decision summary: " + json.dumps(result, sort_keys=True))
                require(
                    result is not None and result.get("status") == "decision",
                    "Live provider did not return an accepted typed decision",
                )
                print(
                    "PASS live Decisions API advice evaluated through production Pulse."
                )
        finally:
            for node in nodes:
                node.storage.conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Evaluate a live Decisions API request with bounded model fallback using OPENROUTER_API_KEY",
    )
    args = parser.parse_args()
    try:
        asyncio.run(run_demo(live=args.live))
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
