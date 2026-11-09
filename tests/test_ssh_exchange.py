"""Run the SSH helper lifecycle without connecting to or authorizing peers."""

import asyncio
import importlib.util
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

import pytest

ROOT = Path(__file__).parents[1]


sys.path.append(str(ROOT / "scripts"))
from exchange_ssh_keys import main  # noqa: E402


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "start", "stop"])
async def test_exchange_owns_temporary_state_and_cleans_up_on_failure(
    tmp_path, monkeypatch, failure
):
    spec = importlib.util.spec_from_file_location(
        "exchange_ssh_keys", ROOT / "scripts/exchange_ssh_keys.py"
    )
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    (home / ".ssh/id_ed25519.pub").write_text("ssh-ed25519 own-test-key")
    auth = home / ".ssh/authorized_keys"
    auth.write_text("existing-authorized-key\n")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("SWARM_KEY", "test-swarm-key")
    monkeypatch.setattr(sys, "argv", ["exchange_ssh_keys.py", "--duration", "0"])
    monkeypatch.chdir(tmp_path)
    for name in ("ssh_exchange.db", "ssh_identity.pem"):
        (tmp_path / name).write_text("earlier-owner-state")
    instances = []
    constructor = helper.LiminalMesh

    def create(**kwargs):
        mesh = constructor(**kwargs)  # Real constructor rejects obsolete db_path.
        instances.append((mesh, kwargs))
        return mesh

    start = AsyncMock(
        side_effect=RuntimeError("startup failed") if failure == "start" else None
    )
    stop = AsyncMock(
        side_effect=RuntimeError("stop failed") if failure == "stop" else None
    )
    monkeypatch.setattr(constructor, "start", start)
    monkeypatch.setattr(constructor, "stop", stop)
    monkeypatch.setattr(constructor, "update_set", AsyncMock())
    monkeypatch.setattr(helper, "LiminalMesh", create)
    monkeypatch.setattr(helper.asyncio, "sleep", AsyncMock())
    if failure:
        with pytest.raises(RuntimeError):
            await helper.main()
    else:
        await helper.main()
    mesh, kwargs = instances[0]
    start.assert_awaited_once()
    stop.assert_awaited_once()
    assert not Path(kwargs["identity_path"]).parent.exists()
    with pytest.raises(sqlite3.ProgrammingError):
        mesh.storage.conn.execute("SELECT 1")
    assert auth.read_text() == "existing-authorized-key\n"
    for name in ("ssh_exchange.db", "ssh_identity.pem"):
        assert (tmp_path / name).read_text() == "earlier-owner-state"


def test_setup_default_path_invokes_exchange_without_host_changes(tmp_path):
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    (home / ".ssh/id_ed25519").write_text("existing-test-key")
    (tmp_path / ".venv/bin").mkdir(parents=True)
    (tmp_path / ".venv/bin/activate").touch()
    binaries = tmp_path / "bin"
    binaries.mkdir()
    for name in ("python3", "pip3", "node", "npm", "ssh-keygen"):
        executable = binaries / name
        executable.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALLS"\n')
        executable.chmod(0o755)
    env = dict(
        os.environ,
        HOME=str(home),
        SWARM_KEY="test-swarm",
        CI="true",
        SKIP_SSH_EXCHANGE="",
        CALLS=str(tmp_path / "calls"),
        PATH=str(binaries) + os.pathsep + os.environ["PATH"],
    )
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/setup-ensemble.sh")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (
        "scripts/exchange_ssh_keys.py --duration 30" in (tmp_path / "calls").read_text()
    )
    assert not (home / ".ssh/authorized_keys").exists()
    assert (home / ".ssh/id_ed25519").read_text() == "existing-test-key"


def test_ssh_exchange_logic():
    async def run_test():
        # Mock environment and files
        mock_env = {"SWARM_KEY": "test-key"}
        mock_pubkey_content = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIK..."
        mock_peer_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIL..."

        with patch.dict(os.environ, mock_env), patch(
            "pathlib.Path.home", return_value=Path("/tmp/fakehome")
        ), patch(
            "builtins.open", mock_open(read_data=mock_pubkey_content)
        ) as mocked_file, patch(
            "exchange_ssh_keys.LiminalMesh"
        ) as MockMesh:

            # Configure MockMesh
            mock_mesh_instance = MockMesh.return_value
            mock_mesh_instance.start = MagicMock(return_value=asyncio.Future())
            mock_mesh_instance.start.return_value.set_result(None)
            mock_mesh_instance.stop = MagicMock(return_value=asyncio.Future())
            mock_mesh_instance.stop.return_value.set_result(None)
            mock_mesh_instance.update_set = MagicMock(return_value=asyncio.Future())
            mock_mesh_instance.update_set.return_value.set_result(None)

            # Simulate discovering a peer key immediately
            mock_mesh_instance.get_kv.side_effect = [[mock_peer_key], [mock_peer_key]]

            # Mock Path.exists
            with patch("pathlib.Path.exists", return_value=True):
                # Run main with a short duration
                try:
                    with patch("sys.argv", ["exchange-ssh-keys.py", "--duration", "2"]):
                        await main()
                except SystemExit as e:
                    # main() should return normally; sys.exit is used for early errors
                    assert e.code == 0, f"Unexpected SystemExit with code {e.code}"

            # Verify mesh was started and stopped
            mock_mesh_instance.start.assert_called_once()
            mock_mesh_instance.stop.assert_called_once()

            # Verify my key was shared
            mock_mesh_instance.update_set.assert_called_with(
                "ssh_peer_keys", mock_pubkey_content
            )

            # Verify authorized_keys was opened for appending
            append_calls = [
                call for call in mocked_file.call_args_list if call.args[1] == "a"
            ]
            assert len(append_calls) > 0

    asyncio.run(run_test())
