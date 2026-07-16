import queue
import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class LoadSheddingPolicy(Enum):
    FAIL_FAST = "FAIL_FAST"
    DROP_OLDEST = "DROP_OLDEST"
    DROP_NEWEST = "DROP_NEWEST"
    BACKPRESSURE_WAIT = "BACKPRESSURE_WAIT"


class MailboxFullException(Exception):
    """Exception raised when the mailbox queue is full and FAIL_FAST or BACKPRESSURE_WAIT timeout is triggered."""

    pass


class BoundedMailbox:
    """
    Thread-safe synchronized bounded mailbox queue supporting active load-shedding policies:
    - FAIL_FAST: Immediately raises MailboxFullException if full.
    - DROP_OLDEST: Discards the oldest message, appends the new message, and logs a warning.
    - DROP_NEWEST: Discards the incoming message, and logs a warning.
    - BACKPRESSURE_WAIT: Blocks on insertion with a configurable timeout. Raises MailboxFullException on expiration.
    """

    def __init__(
        self,
        max_size: int = 100,
        policy: LoadSheddingPolicy = LoadSheddingPolicy.FAIL_FAST,
        wait_timeout: float = 1.0,
    ):
        self.max_size = max_size
        self.policy = policy
        self.wait_timeout = wait_timeout
        # We use standard synchronized Queue with maxsize = max_size
        # But since we might want to manually manipulate elements for DROP_OLDEST (non-blocking drops),
        # we can lock and manipulate under thread safety using the queue's internal lock or self lock.
        # Alternatively, Queue has its own mutex which is private (_init/mutex).
        # To be absolutely safe and reliable across python implementations without touching private internals:
        # We use a standard queue.Queue, but we manage the synchronization ourselves or wrap standard queue calls.
        # For DROP_OLDEST, we can do a non-blocking put, or if it is full, do a non-blocking get_nowait to drop oldest,
        # then a put_nowait.
        self._queue = queue.Queue(maxsize=max_size)

    def put(self, message: Any) -> None:
        """
        Inserts a message into the mailbox queue, respecting the configured load-shedding policy.
        """
        if self.policy == LoadSheddingPolicy.FAIL_FAST:
            try:
                self._queue.put_nowait(message)
            except queue.Full:
                raise MailboxFullException(
                    f"Mailbox is full (size={self._queue.qsize()}). Load shedding: FAIL_FAST."
                )

        elif self.policy == LoadSheddingPolicy.DROP_OLDEST:
            # Synchronously drop oldest if full.
            # Using queue's lock or simple loop to ensure we try-put or resolve.
            # Standard thread-safety: we try to put_nowait. If full, we try to pop one (get_nowait), then put again.
            # To handle potential race conditions when multiple producers exist, we loop until success.
            while True:
                try:
                    self._queue.put_nowait(message)
                    break
                except queue.Full:
                    try:
                        dropped = self._queue.get_nowait()
                        logger.warning(
                            f"Mailbox is full. DROP_OLDEST policy discarded oldest message: {dropped}"
                        )
                    except queue.Empty:
                        # Another thread might have cleared it. Just loop and try put again.
                        pass

        elif self.policy == LoadSheddingPolicy.DROP_NEWEST:
            try:
                self._queue.put_nowait(message)
            except queue.Full:
                logger.warning(
                    f"Mailbox is full. DROP_NEWEST policy discarded incoming message: {message}"
                )

        elif self.policy == LoadSheddingPolicy.BACKPRESSURE_WAIT:
            try:
                self._queue.put(message, block=True, timeout=self.wait_timeout)
            except queue.Full:
                raise MailboxFullException(
                    f"Mailbox remained full after waiting {self.wait_timeout}s. Load shedding: BACKPRESSURE_WAIT."
                )

    def get(self, block: bool = True, timeout: float = None) -> Any:
        """
        Retrieves a message from the mailbox queue.
        Raises queue.Empty if empty and timeout or non-blocking.
        """
        return self._queue.get(block=block, timeout=timeout)

    def qsize(self) -> int:
        """Returns the approximate size of the mailbox."""
        return self._queue.qsize()

    def empty(self) -> bool:
        """Returns True if the mailbox is empty."""
        return self._queue.empty()

    def full(self) -> bool:
        """Returns True if the mailbox is full."""
        return self._queue.full()
