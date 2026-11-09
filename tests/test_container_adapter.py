"""Tests for ContainerExecutionAdapter."""

import pytest
import tempfile
import os
from src.core.collaboration.container_adapter import ContainerExecutionAdapter
from src.core.collaboration.adapter import AttemptLimits, IsolationLevel


@pytest.fixture
def temp_ws():
    temp_dir = tempfile.mkdtemp(prefix="polyphony_container_ws_")
    yield temp_dir
    import shutil

    shutil.rmtree(temp_dir, ignore_errors=True)


def test_container_adapter_lifecycle(temp_ws):
    adapter = ContainerExecutionAdapter(
        container_engine="docker",
        base_image="alpine:latest",
        workspace_base=temp_ws,
        simulate_runtime=True,
    )

    caps = adapter.query_capabilities()
    assert caps["isolation_level"] == IsolationLevel.CONTAINER.value
    assert caps["supports_cancellation"] is True

    # Launch
    handle = adapter.launch(
        task_id="t_cnt_1",
        attempt_id="asgn_1",
        fence_token=1,
        actor_id="worker_docker_1",
        baseline_ref="main",
        limits=AttemptLimits(timeout_seconds=60.0, max_memory_mb=256),
    )
    assert handle.handle_id in adapter.active_containers
    ws_dir = handle.metadata["workspace_dir"]
    assert os.path.isdir(ws_dir)

    # Observe
    obs1 = adapter.observe(handle)
    assert obs1.status == "running"

    # Set output
    adapter.set_output(handle, diff_text="diff from container", consumption=3.5)
    obs2 = adapter.observe(handle)
    assert obs2.status == "completed"
    assert obs2.diff_text == "diff from container"
    assert obs2.resource_consumption == 3.5

    # Cancel
    ok_cancel, cost = adapter.cancel(handle)
    assert ok_cancel is True
    assert cost == 3.5
    assert not os.path.exists(ws_dir)
