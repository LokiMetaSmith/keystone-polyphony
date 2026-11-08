"""Worker-side autonomous choice and optional recorded advice, without a conductor.

The service execution template is owner-approved; workers cannot supply commands,
private files, host paths, environment, or alternate acceptance rules over RPC.
"""

import argparse
import asyncio
import os
import secrets

from aiohttp import ClientError

from .coordinator import Conflict, select_task
from .coordinator_service import CoordinatorClient


class Worker:
    def __init__(self, client, identity, capabilities=(), seconds=60):
        self.client = client
        self.identity = identity
        self.capabilities = list(capabilities)
        self.seconds = seconds
        self.attempt = None
        self.cursor = 0

    async def tick(self):
        """One bounded choice. No task means an event wait, never a model call."""
        snapshot = await self.client.snapshot()
        self.cursor = snapshot["cursor"]
        # Reconnect to unfinished work from the same authenticated identity.
        active = next(
            (
                a
                for a in snapshot["attempt"]
                if a["worker"] == self.identity and not a["termination_confirmed"]
            ),
            None,
        )
        if active:
            if active["state"] == "reserved":
                await self.client.request(
                    "POST", "/execute", {"attempt_id": active["id"]}
                )
            self.attempt = active["id"]
            return "waiting_for_execution"
        task = select_task(snapshot, self.capabilities, self.seconds)
        if task is None:
            return "waiting_for_work"
        # Advice cannot alter requirements or block independent choice.
        responded = {(r["advice"], r["worker"]) for r in snapshot["response"]}
        for advice in snapshot["advice"]:
            if (
                advice["task"] == task["id"]
                and (advice["id"], self.identity) not in responded
            ):
                try:
                    await self.client.call(
                        "respond",
                        advice_id=advice["id"],
                        response="defer",
                        cause="worker selected permitted work using capability, age and budget",
                    )
                except Conflict:
                    pass  # expired advice is not a reason to stop work
        attempt = await self.client.call(
            "start_attempt",
            task_id=task["id"],
            capabilities=self.capabilities,
            seconds=self.seconds,
            request_key=secrets.token_hex(16),
        )
        self.attempt = attempt["id"]
        await self.client.request("POST", "/execute", {"attempt_id": attempt["id"]})
        return "started"

    async def run(self, stop):
        while not stop.is_set():
            try:
                await self.tick()
                await self.client.wait(self.cursor)
            except (ClientError, OSError, asyncio.TimeoutError, Conflict):
                # A network outage does not create a fresh attempt/budget or
                # authorize a protected write. Existing local work keeps running.
                try:
                    await asyncio.wait_for(stop.wait(), timeout=1)
                except asyncio.TimeoutError:
                    pass


async def advise_from_problems(client):
    """Optional non-coding conductor; it has no enrollment/launch/accept rights."""
    snapshot = await client.snapshot()
    for task in snapshot["task"]:
        problems = [
            p
            for p in snapshot["problem"]
            if p["task"] == task["id"] and p["input_revision"] == task["revision"]
        ]
        if problems and task["status"] != "accepted":
            try:
                await client.call(
                    "advise",
                    task_id=task["id"],
                    message="Consider another ready task or propose a smaller interface to the task owner; "
                    "record unresolved work when the task budget ends.",
                )
            except Conflict:
                pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8766")
    parser.add_argument("--identity", required=True)
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--capability", action="append", default=[])
    args = parser.parse_args()
    client = CoordinatorClient(args.url, os.environ["POLYPHONY_WORKER_TOKEN"])
    asyncio.run(
        Worker(client, args.identity, args.capability, args.seconds).run(
            asyncio.Event()
        )
    )


if __name__ == "__main__":
    main()
