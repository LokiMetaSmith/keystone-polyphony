import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

# Ensure we can import scripts
sys.path.append(os.path.abspath("scripts"))
# Ensure we can import src
sys.path.append(os.path.abspath("src"))

from exchange_ssh_keys import main  # noqa: E402


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
                except SystemExit:
                    pass

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
