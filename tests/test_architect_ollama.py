import os
import pytest
from unittest.mock import AsyncMock, patch
from src.liminal_bridge.architect import Architect


@pytest.mark.asyncio
async def test_architect_detects_ollama_provider_via_env():
    with patch.dict(os.environ, {"DUCKY_PROVIDER": "ollama", "DUCKY_MODEL": "llama2"}):
        with patch("ollama.AsyncClient", return_value=AsyncMock()):
            arch = Architect()
            assert arch.provider == "ollama"
            assert arch.client is not None


@pytest.mark.asyncio
async def test_architect_detects_ollama_provider_via_model_prefix():
    # Ensure DUCKY_PROVIDER is not interfering
    with patch.dict(os.environ, {}, clear=True):
        with patch.dict(os.environ, {"DUCKY_MODEL": "ollama:llama3"}):
            with patch("ollama.AsyncClient", return_value=AsyncMock()):
                arch = Architect()
                assert arch.provider == "ollama"
                assert arch.model == "llama3"
                assert arch.client is not None


@pytest.mark.asyncio
async def test_consult_ollama():
    with patch.dict(os.environ, {"DUCKY_PROVIDER": "ollama", "DUCKY_MODEL": "llama2"}):
        with patch("ollama.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            MockClient.return_value = mock_client_instance

            # Mock the chat response
            mock_client_instance.chat.return_value = {
                "message": {"content": '{"backlog": ["task1"]}'}
            }

            arch = Architect()
            result = await arch.consult({})

            assert '{"backlog": ["task1"]}' in result
            mock_client_instance.chat.assert_called_once()
            call_args = mock_client_instance.chat.call_args[1]
            assert call_args["model"] == "llama2"
            assert call_args["format"] == "json"


@pytest.mark.asyncio
async def test_refine_issue_ollama():
    with patch.dict(os.environ, {"DUCKY_PROVIDER": "ollama", "DUCKY_MODEL": "llama2"}):
        with patch("ollama.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            MockClient.return_value = mock_client_instance

            mock_client_instance.chat.return_value = {
                "message": {"content": "Refined Issue Content"}
            }

            arch = Architect()
            result = await arch.refine_issue("Raw issue")

            assert result == "Refined Issue Content"
            mock_client_instance.chat.assert_called_once()
            call_args = mock_client_instance.chat.call_args[1]
            assert call_args["model"] == "llama2"
            # refine_issue doesn't use format="json"
            assert "format" not in call_args
