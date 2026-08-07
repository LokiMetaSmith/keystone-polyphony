import pytest
from src.liminal_bridge.crdt import RevisionLog


def test_revision_log_append_and_value():
    log = RevisionLog()
    log.append(100.0, "alice", "rev-1", "diff1")
    log.append(200.0, "bob", "rev-2", "diff2")

    val = log.value()
    assert len(val) == 2
    assert val[0]["timestamp"] == 100.0
    assert val[0]["author"] == "alice"
    assert val[0]["diff"] == "diff1"

    assert val[1]["timestamp"] == 200.0
    assert val[1]["diff"] == "diff2"


def test_revision_log_merge():
    log1 = RevisionLog()
    log1.append(100.0, "alice", "rev-1", "diff1")

    log2 = RevisionLog()
    log2.append(200.0, "bob", "rev-2", "diff2")

    log1.merge(log2)
    val = log1.value()
    assert len(val) == 2
    assert val[0]["author"] == "alice"
    assert val[1]["author"] == "bob"


def test_revision_log_serialization():
    log = RevisionLog()
    log.append(100.0, "alice", "rev-1", "diff1")

    data = log.to_dict()
    assert data["type"] == "revision-log"
    assert len(data["revisions"]) == 1

    log2 = RevisionLog.from_dict(data)
    assert log2.value()[0]["diff"] == "diff1"
