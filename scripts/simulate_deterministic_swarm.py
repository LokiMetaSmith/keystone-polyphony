#!/usr/bin/env python3
import sys
import os
from dataclasses import dataclass

# Add src to the path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.isolate import BaseIsolate
from src.core.mailbox import BoundedMailbox, LoadSheddingPolicy
from src.core.effects import LogEffect, SendMessageEffect, PersistStateEffect, ScheduleTimeoutEffect
from src.runtime.deterministic_scheduler import DeterministicScheduler

@dataclass
class SwarmState:
    task_count: int
    has_baton: bool
    persisted_count: int

@dataclass(frozen=True)
class StartTaskMessage:
    task_id: str

@dataclass(frozen=True)
class TaskUpdateMessage:
    task_id: str
    status: str

@dataclass(frozen=True)
class PersistAckMessage:
    persisted_count: int


class SeniorDevIsolate(BaseIsolate):
    def handle_message(self, msg):
        if isinstance(msg, StartTaskMessage):
            self.state.task_count += 1
            effects = [
                LogEffect(level="INFO", message=f"Starting task: {msg.task_id}"),
                SendMessageEffect(target_mailbox_id="JuniorDev", message=TaskUpdateMessage(task_id=msg.task_id, status="IN_PROGRESS")),
                ScheduleTimeoutEffect(delay_ticks=15, message=TaskUpdateMessage(task_id=msg.task_id, status="COMPLETED")),
            ]
            return effects

        elif isinstance(msg, TaskUpdateMessage) and msg.status == "COMPLETED":
            self.state.has_baton = False
            return [
                LogEffect(level="INFO", message=f"Task {msg.task_id} is completed. Releasing baton."),
                PersistStateEffect(state_delta=SwarmState(task_count=self.state.task_count, has_baton=False, persisted_count=self.state.persisted_count + 1)),
            ]

        return []


class JuniorDevIsolate(BaseIsolate):
    def handle_message(self, msg):
        if isinstance(msg, TaskUpdateMessage):
            self.state.task_count += 1
            self.log_level = "INFO"
            effects = [
                LogEffect(level="INFO", message=f"Received update from Senior: {msg.task_id} is {msg.status}"),
                PersistStateEffect(state_delta=SwarmState(task_count=self.state.task_count, has_baton=self.state.has_baton, persisted_count=self.state.persisted_count + 1))
            ]
            return effects
        return []


def run_simulation(seed: int):
    print(f"\n--- Running Deterministic Swarm Simulation with seed={seed} ---")
    scheduler = DeterministicScheduler(
        seed=seed,
        packet_drop_rate=0.1,  # 10% drop chance
        network_delay_range=(2, 6),
        db_lag_range=(3, 7)
    )

    senior_mailbox = BoundedMailbox(max_size=10, policy=LoadSheddingPolicy.FAIL_FAST)
    junior_mailbox = BoundedMailbox(max_size=10, policy=LoadSheddingPolicy.FAIL_FAST)

    senior_iso = SeniorDevIsolate(initial_state=SwarmState(task_count=0, has_baton=True, persisted_count=0))
    junior_iso = JuniorDevIsolate(initial_state=SwarmState(task_count=0, has_baton=False, persisted_count=0))

    scheduler.register_agent("SeniorDev", senior_iso, senior_mailbox)
    scheduler.register_agent("JuniorDev", junior_iso, junior_mailbox)

    # Bootstrap events
    scheduler.schedule_event(0, scheduler.dispatch_message, "SeniorDev", StartTaskMessage(task_id="Task-101"))
    scheduler.schedule_event(10, scheduler.dispatch_message, "SeniorDev", StartTaskMessage(task_id="Task-102"))

    # Run loop
    scheduler.run_until_idle(max_ticks=200)

    # Print traces
    for line in scheduler.trace:
        print(line)

    print(f"\nFinal Senior State: {senior_iso.state}")
    print(f"Final Junior State: {junior_iso.state}")
    return scheduler.trace


def main():
    # Run with seed 12345 twice and verify traces are identical
    trace_run1 = run_simulation(12345)
    trace_run2 = run_simulation(12345)

    assert trace_run1 == trace_run2, "Error: Seeds do not yield identical traces!"
    print("\n✅ DETERMINISM VERIFIED: Both runs yielded 100% identical event sequences!")

    # Run with a different seed to show different execution flow
    run_simulation(54321)


if __name__ == "__main__":
    main()
