import pytest
import time
from dataclasses import dataclass
from src.core.isolate import BaseIsolate
from src.core.mailbox import BoundedMailbox
from src.core.effects import LogEffect, SendMessageEffect
from src.runtime.tpc_executor import TpcExecutor, pin_to_core

@dataclass
class SimpleState:
    count: int

@dataclass(frozen=True)
class IncrementMessage:
    amount: int

class DummyIsolate(BaseIsolate):
    def handle_message(self, msg: IncrementMessage):
        self.state.count += msg.amount
        return [
            LogEffect(level="INFO", message=f"Incremented by {msg.amount}, total is {self.state.count}"),
            SendMessageEffect(target_mailbox_id="dummy_target", message="Done")
        ]

def test_pin_to_core_fallback():
    # Calling pin_to_core should run without crash, returning True or False depending on platform support
    res = pin_to_core(0)
    assert isinstance(res, bool)

def test_tpc_executor():
    isolate = DummyIsolate(SimpleState(count=0))
    mailbox = BoundedMailbox(max_size=10)

    dispatched_effects = []
    def dispatcher(sender, effect):
        dispatched_effects.append((sender, effect))

    executor = TpcExecutor(
        executor_id="dummy_exec",
        isolate=isolate,
        mailbox=mailbox,
        core_id=0,
        effect_dispatcher=dispatcher
    )

    executor.start()

    mailbox.put(IncrementMessage(amount=5))
    mailbox.put(IncrementMessage(amount=3))

    # Wait a bit for processing
    time.sleep(0.5)

    executor.stop()

    assert isolate.state.count == 8
    assert len(dispatched_effects) == 2
    sender, effect = dispatched_effects[0]
    assert sender == "dummy_exec"
    assert isinstance(effect, SendMessageEffect)
    assert effect.target_mailbox_id == "dummy_target"
    assert effect.message == "Done"
