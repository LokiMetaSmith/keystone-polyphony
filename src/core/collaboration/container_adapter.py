"""Container/Sandbox Execution Adapter for multi-tenant worker isolation."""

import os
import subprocess
import shutil
import uuid
from typing import Dict, Any, Optional, Tuple, List
from .adapter import (
    BaseExecutionAdapter,
    AttemptHandle,
    AttemptObservation,
    AttemptLimits,
    IsolationLevel,
)


class ContainerExecutionAdapter(BaseExecutionAdapter):
    """
    Executes attempts inside isolated container runtimes (Docker/Podman)
    or simulated sandboxes with resource envelopes (CPU/RAM) and strict cancellations.
    """

    def __init__(
        self,
        container_engine: str = "docker",
        base_image: str = "alpine:latest",
        workspace_base: Optional[str] = None,
        simulate_runtime: bool = False,
    ):
        self.container_engine = container_engine
        self.base_image = base_image
        self.simulate_runtime = simulate_runtime
        self.workspace_base = os.path.abspath(
            workspace_base or os.path.join(os.getcwd(), ".polyphony", "containers")
        )
        os.makedirs(self.workspace_base, exist_ok=True)
        self.active_containers: Dict[str, Dict[str, Any]] = {}

    def query_capabilities(self) -> Dict[str, Any]:
        return {
            "isolation_level": IsolationLevel.CONTAINER.value,
            "supports_cancellation": True,
            "supports_resource_limiting": True,
            "container_engine": self.container_engine,
            "base_image": self.base_image,
        }

    def launch(
        self,
        task_id: str,
        attempt_id: str,
        fence_token: int,
        actor_id: str,
        baseline_ref: str,
        limits: Optional[AttemptLimits] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AttemptHandle:
        handle_id = f"cnt_{uuid.uuid4().hex[:12]}"
        limits = limits or AttemptLimits()
        container_name = f"polyphony_{attempt_id}_{handle_id}"
        workspace_dir = os.path.join(self.workspace_base, container_name)
        os.makedirs(workspace_dir, exist_ok=True)

        handle = AttemptHandle(
            handle_id=handle_id,
            task_id=task_id,
            attempt_id=attempt_id,
            fence_token=fence_token,
            actor_id=actor_id,
            baseline_ref=baseline_ref,
            limits=limits,
            metadata={
                "container_name": container_name,
                "workspace_dir": workspace_dir,
                **(metadata or {}),
            },
        )

        if not self.simulate_runtime:
            cmd = [
                self.container_engine,
                "run",
                "-d",
                "--name",
                container_name,
                "-m",
                f"{limits.max_memory_mb}m",
                "-v",
                f"{workspace_dir}:/workspace",
                self.base_image,
                "sleep",
                str(int(limits.timeout_seconds)),
            ]
            try:
                subprocess.run(
                    cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
            except Exception as e:
                shutil.rmtree(workspace_dir, ignore_errors=True)
                raise RuntimeError(f"Failed to launch container: {e}")

        self.active_containers[handle_id] = {
            "container_name": container_name,
            "workspace_dir": workspace_dir,
            "status": "running",
            "consumption": 1.0,
            "diff_text": "",
        }

        return handle

    def set_output(
        self, handle: AttemptHandle, diff_text: str, consumption: float = 2.0
    ) -> None:
        if handle.handle_id in self.active_containers:
            self.active_containers[handle.handle_id]["diff_text"] = diff_text
            self.active_containers[handle.handle_id]["consumption"] = consumption
            self.active_containers[handle.handle_id]["status"] = "completed"

    def observe(self, handle: AttemptHandle) -> AttemptObservation:
        info = self.active_containers.get(handle.handle_id)
        if not info:
            return AttemptObservation(
                handle_id=handle.handle_id,
                status="unknown",
                resource_consumption=0.0,
                error="Container handle not found",
            )

        return AttemptObservation(
            handle_id=handle.handle_id,
            status=info["status"],
            resource_consumption=info["consumption"],
            diff_text=info.get("diff_text"),
        )

    def cancel(self, handle: AttemptHandle) -> Tuple[bool, float]:
        info = self.active_containers.get(handle.handle_id)
        if not info:
            return True, 0.0

        container_name = info["container_name"]
        workspace_dir = info["workspace_dir"]

        if not self.simulate_runtime:
            subprocess.run(
                [self.container_engine, "rm", "-f", container_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        if os.path.exists(workspace_dir):
            shutil.rmtree(workspace_dir, ignore_errors=True)

        cost = info["consumption"]
        info["status"] = "cancelled"
        del self.active_containers[handle.handle_id]
        return True, cost
