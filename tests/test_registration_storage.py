import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["sqlite", "redis", "postgres"])
@pytest.mark.parametrize("replacing", [False, True])
async def test_registration_preserves_storage_configuration(
    monkeypatch, backend, replacing
):
    monkeypatch.setenv("SWARM_KEY", "registration-test-key")
    server = importlib.import_module("src.liminal_bridge.server")
    old_mesh = SimpleNamespace(secret_key="old-key", running=True, stop=AsyncMock())
    mesh = SimpleNamespace(
        secret_key="new-key",
        running=False,
        start=AsyncMock(),
        node_id="node",
        topic="test-topic",
    )
    provider = object()
    create_storage = Mock(return_value=provider)
    create_mesh = Mock(return_value=mesh)
    pulse = SimpleNamespace(on_baton_release=AsyncMock())
    monkeypatch.setattr(server, "mesh", old_mesh if replacing else None)
    monkeypatch.setattr(server, "pulse", None)
    monkeypatch.setattr(server, "args", None)
    monkeypatch.setattr(server, "dashboard_server", None)
    monkeypatch.setattr(server, "STORAGE_BACKEND", backend)
    monkeypatch.setattr(server, "STORAGE_URL", "configured-url")
    monkeypatch.setattr(server, "DB_PATH", "configured.db")
    monkeypatch.setattr(server, "_create_storage_provider", create_storage)
    monkeypatch.setattr(server, "LiminalMesh", create_mesh)
    monkeypatch.setattr(server, "Pulse", Mock(return_value=pulse))

    result = await server.register_to_swarm("new-key")

    create_storage.assert_called_once_with(backend, "configured.db", "configured-url")
    assert create_mesh.call_args.kwargs["storage_provider"] is provider
    assert create_mesh.call_args.kwargs["secret_key"] == "new-key"
    assert mesh.on_command_request is server.handle_command_request
    assert mesh.on_baton_release is pulse.on_baton_release
    mesh.start.assert_awaited_once()
    if replacing:
        old_mesh.stop.assert_awaited_once()
    assert "Connected to Liminal Swarm" in result
