import random
import heapq
import logging
from typing import Any, List, Dict, Tuple, Callable
from src.core.isolate import BaseIsolate
from src.core.mailbox import BoundedMailbox
from src.core.effects import (
    BaseEffect,
    SendMessageEffect,
    PersistStateEffect,
    LogEffect,
    ScheduleTimeoutEffect,
)

logger = logging.getLogger(__name__)


class DeterministicScheduler:
    """
    Manages and coordinates a deterministic simulation of multi-agent isolates.
    Operates on a single thread with a virtual logical clock.
    Uses a seeded pseudo-random number generator to simulate:
    - Network packet drop
    - Network delivery latency (delays)
    - Database write lag

    All execution flows are 100% reproducible for a given seed.
    """

    def __init__(
        self,
        seed: int = 42,
        packet_drop_rate: float = 0.05,
        network_delay_range: Tuple[int, int] = (1, 10),
        db_lag_range: Tuple[int, int] = (2, 5),
    ):
        self.random = random.Random(seed)
        self.packet_drop_rate = packet_drop_rate
        self.network_delay_range = network_delay_range
        self.db_lag_range = db_lag_range

        self.current_time = 0
        self.event_counter = 0
        # Priority queue stores: (scheduled_time, event_counter, callback, args)
        self.events = []

        self.isolates: Dict[str, BaseIsolate] = {}
        self.mailboxes: Dict[str, BoundedMailbox] = {}
        self.trace: List[str] = []

    def register_agent(
        self, agent_id: str, isolate: BaseIsolate, mailbox: BoundedMailbox
    ):
        self.isolates[agent_id] = isolate
        self.mailboxes[agent_id] = mailbox

    def schedule_event(self, delay: int, callback: Callable, *args):
        scheduled_time = self.current_time + delay
        self.event_counter += 1
        heapq.heappush(
            self.events, (scheduled_time, self.event_counter, callback, args)
        )

    def log_trace(self, message: str):
        msg = f"[T={self.current_time}] {message}"
        self.trace.append(msg)
        logger.debug(msg)

    def dispatch_message(self, target_mailbox_id: str, msg: Any):
        """Dispatches a message immediately (or attempts to) to a mailbox."""
        mailbox = self.mailboxes.get(target_mailbox_id)
        if not mailbox:
            self.log_trace(f"ERROR: Mailbox {target_mailbox_id} not found.")
            return

        try:
            mailbox.put(msg)
            # Instantly process the message for this mailbox (Single-threaded execution step)
            # To simulate processing time/steps, we handle it sequentially:
            self._execute_isolate_step(target_mailbox_id)
        except Exception as e:
            self.log_trace(
                f"Shed/Dropped message to {target_mailbox_id} due to: {e.__class__.__name__}"
            )

    def _execute_isolate_step(self, agent_id: str):
        isolate = self.isolates[agent_id]
        mailbox = self.mailboxes[agent_id]
        if mailbox.empty():
            return

        msg = mailbox.get()
        self.log_trace(f"{agent_id} processing message: {msg}")
        effects = isolate.handle_message(msg)

        for effect in effects:
            self._process_effect(agent_id, effect)

    def _process_effect(self, agent_id: str, effect: BaseEffect):
        if isinstance(effect, LogEffect):
            self.log_trace(f"LOG ({effect.level}) from {agent_id}: {effect.message}")

        elif isinstance(effect, PersistStateEffect):
            # Simulate DB lag
            db_lag = self.random.randint(*self.db_lag_range)
            self.log_trace(
                f"DB Write started for {agent_id}. Simulating DB write lag of {db_lag} ticks."
            )

            def commit_state(aid, delta):
                self.isolates[aid].state = delta
                self.log_trace(
                    f"DB Write completed/committed for {aid}. State updated."
                )

            self.schedule_event(db_lag, commit_state, agent_id, effect.state_delta)

        elif isinstance(effect, SendMessageEffect):
            # Simulating network: drop or delay
            if self.random.random() < self.packet_drop_rate:
                self.log_trace(
                    f"NETWORK DROP: Message from {agent_id} to {effect.target_mailbox_id} dropped."
                )
            else:
                delay = self.random.randint(*self.network_delay_range)
                self.log_trace(
                    f"NETWORK DELAY: Message from {agent_id} to {effect.target_mailbox_id} delayed by {delay} ticks."
                )
                self.schedule_event(
                    delay,
                    self.dispatch_message,
                    effect.target_mailbox_id,
                    effect.message,
                )

        elif isinstance(effect, ScheduleTimeoutEffect):
            target = effect.target_mailbox_id if effect.target_mailbox_id else agent_id
            self.log_trace(
                f"TIMEOUT SCHEDULED: {agent_id} scheduled message to {target} in {effect.delay_ticks} ticks."
            )
            self.schedule_event(
                effect.delay_ticks, self.dispatch_message, target, effect.message
            )

    def step(self) -> bool:
        """
        Advances the virtual clock to the next scheduled event time and processes it.
        Returns False if no events are left, True otherwise.
        """
        if not self.events:
            return False

        scheduled_time, _, callback, args = heapq.heappop(self.events)
        self.current_time = scheduled_time
        callback(*args)
        return True

    def run_until_idle(self, max_ticks: int = 1000):
        """Runs the simulation loop until no events remain or max_ticks limit is reached."""
        while self.events and self.current_time < max_ticks:
            self.step()
