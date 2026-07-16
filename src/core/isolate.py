from abc import ABC, abstractmethod
from typing import Any, List
from src.core.effects import BaseEffect


class BaseIsolate(ABC):
    """
    Abstract Base Class for an Isolate.
    Isolates are share-nothing, single-threaded agent boundaries.
    They manage internal state and handle messages in a synchronous pure-like method.
    """

    def __init__(self, initial_state: Any = None, isolate_id: str = ""):
        self.isolate_id = isolate_id
        # Support both initial_state and state dict initialization
        self.state = initial_state if initial_state is not None else {}

    @abstractmethod
    def handle_message(self, msg: Any) -> List[BaseEffect]:
        """
        Processes an incoming message synchronously.
        Must NOT have inline side-effects (async/await, network, DB calls, etc.).
        Returns a list of BaseEffect actions to be processed by the runtime.
        """
        pass
