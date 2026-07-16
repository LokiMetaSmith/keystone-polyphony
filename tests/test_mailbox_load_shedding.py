import pytest
import queue
from src.core.mailbox import BoundedMailbox, LoadSheddingPolicy, MailboxFullException


def test_mailbox_fail_fast():
    mailbox = BoundedMailbox(max_size=2, policy=LoadSheddingPolicy.FAIL_FAST)
    mailbox.put("msg1")
    mailbox.put("msg2")
    with pytest.raises(MailboxFullException):
        mailbox.put("msg3")


def test_mailbox_drop_oldest():
    mailbox = BoundedMailbox(max_size=2, policy=LoadSheddingPolicy.DROP_OLDEST)
    mailbox.put("msg1")
    mailbox.put("msg2")
    mailbox.put("msg3")  # This should drop "msg1" and insert "msg3"

    assert mailbox.get() == "msg2"
    assert mailbox.get() == "msg3"
    assert mailbox.empty()


def test_mailbox_drop_newest():
    mailbox = BoundedMailbox(max_size=2, policy=LoadSheddingPolicy.DROP_NEWEST)
    mailbox.put("msg1")
    mailbox.put("msg2")
    mailbox.put("msg3")  # This should discard "msg3" silently

    assert mailbox.get() == "msg1"
    assert mailbox.get() == "msg2"
    assert mailbox.empty()


def test_mailbox_backpressure_wait():
    mailbox = BoundedMailbox(
        max_size=2, policy=LoadSheddingPolicy.BACKPRESSURE_WAIT, wait_timeout=0.1
    )
    mailbox.put("msg1")
    mailbox.put("msg2")
    with pytest.raises(MailboxFullException):
        mailbox.put("msg3")
