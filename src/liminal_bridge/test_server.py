import os
import sys
import pytest


def test_swarm_key_fallback_generates_random_key(monkeypatch, capsys):
    # Ensure SWARM_KEY is not in environment
    monkeypatch.delenv("SWARM_KEY", raising=False)

    # If server is already in sys.modules, remove it to force re-evaluation of its top-level code
    for key in list(sys.modules.keys()):
        if (
            "liminal_bridge.server" in key
            or "src.liminal_bridge.server" in key
            or key == "server"
        ):
            del sys.modules[key]

    # Import server module
    try:
        from src.liminal_bridge import server
    except ImportError:
        import liminal_bridge.server as server

    # Assert SWARM_KEY is generated and is a 64-char hex string (32 bytes)
    assert server.SWARM_KEY is not None
    assert len(server.SWARM_KEY) == 64
    # Ensure it's a valid hex string
    int(server.SWARM_KEY, 16)

    # Assert that warning was printed to stderr
    captured = capsys.readouterr()
    assert "WARNING: SWARM_KEY environment variable is not set." in captured.err
