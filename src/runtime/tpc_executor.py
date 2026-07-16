import os
import logging
import threading
import queue
from typing import Any, Callable, Dict
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


def pin_to_core(core_id: int) -> bool:
    """
    Attempts to pin the current process/thread to a specific CPU core using sched_setaffinity.
    Provides a graceful fallback if the feature is not supported on the host OS.
    """
    if hasattr(os, "sched_setaffinity"):
        try:
            os.sched_setaffinity(0, {core_id})
            logger.info(
                f"Successfully pinned executor thread/process to CPU core {core_id}"
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to set CPU affinity to core {core_id}: {e}")
            return False
    else:
        logger.warning(
            "Core pinning (sched_setaffinity) is not supported on this platform. Operating on default OS scheduler threads."
        )
        return False


class TpcExecutor:
    """
    Thread-Per-Core (TPC) Executor managing a single Isolate.
    Pins its executor thread to a designated CPU core, pops messages from the isolate's BoundedMailbox,
    runs handle_message inside a synchronous execution loop, and interprets the returned Effects.
    """

    def __init__(
        self,
        executor_id: str,
        isolate: BaseIsolate,
        mailbox: BoundedMailbox,
        core_id: int = None,
        effect_dispatcher: Callable[[str, BaseEffect], None] = None,
    ):
        self.executor_id = executor_id
        self.isolate = isolate
        self.mailbox = mailbox
        self.core_id = core_id
        self.effect_dispatcher = effect_dispatcher

        self._running = False
        self._thread = None

    def start(self):
        """Starts the execution loop thread."""
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, name=f"TPC-Executor-{self.executor_id}"
        )
        self._thread.daemon = True
        self._thread.start()

    def stop(self):
        """Signals the loop thread to stop and waits for it."""
        self._running = False
        # Put a sentinel or wake up the thread if blocked
        # We can put None or a stop sentinel if get is blocking.
        # But wait, we shouldn't necessarily assume get has a sentinel if there are other messages.
        # So we can just put a custom 'STOP' or check empty under timeout.
        # Let's put a custom sentinel to instantly exit.
        try:
            self.mailbox.put("__STOP__")
        except Exception:
            pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _run_loop(self):
        """Internal worker thread loop."""
        if self.core_id is not None:
            pin_to_core(self.core_id)

        while self._running:
            try:
                # Block for up to 0.5s so we can periodically check self._running
                msg = self.mailbox.get(block=True, timeout=0.5)
                if msg == "__STOP__":
                    break

                self._process_message(msg)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(
                    f"Error in TpcExecutor '{self.executor_id}' loop: {e}",
                    exc_info=True,
                )

    def _process_message(self, msg: Any):
        """Executes the isolate message handler and routes the produced effects."""
        effects = self.isolate.handle_message(msg)
        if not effects:
            return

        for effect in effects:
            self._handle_effect(effect)

    def _handle_effect(self, effect: BaseEffect):
        """Interprets a single declarative effect payload."""
        if isinstance(effect, LogEffect):
            lvl = effect.level.upper()
            numeric_level = getattr(logging, lvl, logging.INFO)
            logger.log(numeric_level, f"[{self.executor_id}] {effect.message}")

        elif isinstance(effect, PersistStateEffect):
            # Write state out-of-band. For standard executors, we might just update the isolate's state
            # or delegate to dispatcher
            if self.effect_dispatcher:
                self.effect_dispatcher(self.executor_id, effect)
            else:
                self.isolate.state = effect.state_delta

        elif isinstance(effect, SendMessageEffect):
            if self.effect_dispatcher:
                self.effect_dispatcher(self.executor_id, effect)
            else:
                logger.warning(
                    f"No effect dispatcher configured. SendMessageEffect dropped: {effect}"
                )

        elif isinstance(effect, ScheduleTimeoutEffect):
            if self.effect_dispatcher:
                self.effect_dispatcher(self.executor_id, effect)
            else:
                logger.warning(
                    f"No effect dispatcher configured. ScheduleTimeoutEffect dropped: {effect}"
                )

        else:
            if self.effect_dispatcher:
                self.effect_dispatcher(self.executor_id, effect)
            else:
                logger.warning(f"Unknown effect encountered: {effect}")
