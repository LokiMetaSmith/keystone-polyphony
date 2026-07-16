import pytest
from scripts.simulate_deterministic_swarm import SwarmState, StartTaskMessage, SeniorDevIsolate, JuniorDevIsolate
from src.core.mailbox import BoundedMailbox, LoadSheddingPolicy
from src.runtime.deterministic_scheduler import DeterministicScheduler

def run_single_simulation_to_trace(seed: int) -> list:
    scheduler = DeterministicScheduler(
        seed=seed,
        packet_drop_rate=0.2,  # Inject higher drop rate to make it hard
        network_delay_range=(1, 15),
        db_lag_range=(3, 10)
    )

    senior_mailbox = BoundedMailbox(max_size=10, policy=LoadSheddingPolicy.FAIL_FAST)
    junior_mailbox = BoundedMailbox(max_size=10, policy=LoadSheddingPolicy.FAIL_FAST)

    senior_iso = SeniorDevIsolate(initial_state=SwarmState(task_count=0, has_baton=True, persisted_count=0))
    junior_iso = JuniorDevIsolate(initial_state=SwarmState(task_count=0, has_baton=False, persisted_count=0))

    scheduler.register_agent("SeniorDev", senior_iso, senior_mailbox)
    scheduler.register_agent("JuniorDev", junior_iso, junior_mailbox)

    # Schedule initial messages
    scheduler.schedule_event(0, scheduler.dispatch_message, "SeniorDev", StartTaskMessage(task_id="Task-1"))
    scheduler.schedule_event(5, scheduler.dispatch_message, "SeniorDev", StartTaskMessage(task_id="Task-2"))
    scheduler.schedule_event(10, scheduler.dispatch_message, "SeniorDev", StartTaskMessage(task_id="Task-3"))

    # Run
    scheduler.run_until_idle(max_ticks=500)
    return scheduler.trace

def test_swarm_dst_determinism_across_100_runs():
    """
    Verifies that for a given random seed, the execution sequence and final state
    of all agents are 100% identical on every run across 100 runs.
    """
    seed = 98765

    # Run first time to establish reference trace
    reference_trace = run_single_simulation_to_trace(seed)
    assert len(reference_trace) > 0, "Reference trace is empty!"

    for run_idx in range(1, 100):
        current_trace = run_single_simulation_to_trace(seed)
        assert current_trace == reference_trace, f"Determinism broken at run {run_idx} for seed {seed}!"

    print(f"Successfully verified absolute determinism across 100 runs for seed {seed}.")
