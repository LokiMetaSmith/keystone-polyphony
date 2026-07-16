import os
import sys
import pytest
import tempfile
import shutil
from src.liminal_bridge.auth import get_or_create_swarm_key


def test_get_or_create_swarm_key_from_env(monkeypatch):
    monkeypatch.setenv("SWARM_KEY", "TEST_ENV_KEY")
    key = get_or_create_swarm_key()
    assert key == "TEST_ENV_KEY"


def test_get_or_create_swarm_key_fallback_generates_and_saves(monkeypatch, tmp_path):
    # Ensure SWARM_KEY is not in environment
    monkeypatch.delenv("SWARM_KEY", raising=False)

    # Mock the project root inside auth.py by mocking os.path.abspath/os.path.exists
    temp_dir = str(tmp_path)

    original_dirname = os.path.dirname

    def mock_dirname(path):
        if "auth.py" in path:
            return "/mock/src/liminal_bridge"
        if path == "/mock/src/liminal_bridge":
            return "/mock/src"
        if path == "/mock/src":
            return temp_dir
        return original_dirname(path)

    monkeypatch.setattr(os.path, "dirname", mock_dirname)

    # Run get_or_create_swarm_key
    key = get_or_create_swarm_key()

    assert key is not None
    assert len(key) == 64
    int(key, 16)  # Ensure it is hex

    # Verify it was saved in .swarm_key inside our mocked temp project root
    saved_key_file = os.path.join(temp_dir, ".swarm_key")
    assert os.path.exists(saved_key_file)
    with open(saved_key_file, "r") as f:
        saved_key = f.read().strip()
    assert saved_key == key


def test_get_or_create_swarm_key_reads_saved_key(monkeypatch, tmp_path):
    monkeypatch.delenv("SWARM_KEY", raising=False)
    temp_dir = str(tmp_path)

    # Create a pre-existing .swarm_key file
    saved_key_file = os.path.join(temp_dir, ".swarm_key")
    with open(saved_key_file, "w") as f:
        f.write("PRE_EXISTING_SWARM_KEY\n")

    original_dirname = os.path.dirname

    def mock_dirname(path):
        if "auth.py" in path:
            return "/mock/src/liminal_bridge"
        if path == "/mock/src/liminal_bridge":
            return "/mock/src"
        if path == "/mock/src":
            return temp_dir
        return original_dirname(path)

    monkeypatch.setattr(os.path, "dirname", mock_dirname)

    key = get_or_create_swarm_key()
    assert key == "PRE_EXISTING_SWARM_KEY"


def test_get_or_create_swarm_key_reads_env_file(monkeypatch, tmp_path):
    monkeypatch.delenv("SWARM_KEY", raising=False)
    temp_dir = str(tmp_path)

    # Create a pre-existing .env file with SWARM_KEY
    env_file = os.path.join(temp_dir, ".env")
    with open(env_file, "w") as f:
        f.write("SWARM_KEY=PRE_EXISTING_ENV_KEY\n")

    original_dirname = os.path.dirname

    def mock_dirname(path):
        if "auth.py" in path:
            return "/mock/src/liminal_bridge"
        if path == "/mock/src/liminal_bridge":
            return "/mock/src"
        if path == "/mock/src":
            return temp_dir
        return original_dirname(path)

    monkeypatch.setattr(os.path, "dirname", mock_dirname)

    key = get_or_create_swarm_key()
    assert key == "PRE_EXISTING_ENV_KEY"
