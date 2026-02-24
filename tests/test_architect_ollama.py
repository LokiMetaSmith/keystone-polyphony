import pytest
import sys
import os
from unittest.mock import patch, MagicMock, AsyncMock

# Create a mock ollama module
mock_ollama_module = MagicMock()
sys.modules["ollama"] = mock_ollama_module

# Now import Architect, which will use the mock
from src.liminal_bridge.architect import Architect

@pytest.fixture
def mock_ollama():
    mock_client = MagicMock()
    mock_client.chat = AsyncMock()
    mock_ollama_module.AsyncClient.return_value = mock_client
    return mock_client

@pytest.mark.asyncio
async def test_architect_initialization_ollama_env(mock_ollama):
    with patch.dict(os.environ, {"DUCKY_PROVIDER": "ollama"}):
        architect = Architect()
        assert architect.provider == "ollama"
        assert architect.client == mock_ollama
        mock_ollama_module.AsyncClient.assert_called()

@pytest.mark.asyncio
async def test_architect_initialization_ollama_model(mock_ollama):
    architect = Architect(model="ollama:llama2")
    assert architect.provider == "ollama"
    assert architect.model == "llama2"
    assert architect.client == mock_ollama

@pytest.mark.asyncio
async def test_consult_ollama(mock_ollama):
    mock_ollama.chat.return_value = {"message": {"content": "Test Response"}}

    with patch.dict(os.environ, {"DUCKY_PROVIDER": "ollama"}):
        architect = Architect()
        response = await architect.consult({"state": "test"})

        assert response == "Test Response"
        mock_ollama.chat.assert_called_once()
        args, kwargs = mock_ollama.chat.call_args
        assert kwargs["format"] == "json"

@pytest.mark.asyncio
async def test_refine_issue_ollama(mock_ollama):
    mock_ollama.chat.return_value = {"message": {"content": "Refined Issue"}}

    with patch.dict(os.environ, {"DUCKY_PROVIDER": "ollama"}):
        architect = Architect()
        response = await architect.refine_issue("Raw Issue")

        assert response == "Refined Issue"
        mock_ollama.chat.assert_called_once()
        args, kwargs = mock_ollama.chat.call_args
        assert "format" not in kwargs # refine_issue doesn't use format="json"
