import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import sys
import os

# Ensure src is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.liminal_bridge.architect import Architect  # noqa: E402


@pytest.mark.asyncio
async def test_architect_detects_openai():
    # Patch where it is imported FROM, because the import is local
    with patch("openai.AsyncOpenAI"):
        arch = Architect(api_key="sk-proj-12345")
        assert arch.provider == "openai"
        assert arch.model == "gpt-4o"


@pytest.mark.asyncio
async def test_architect_detects_google():
    # For google, the import is `import google.generativeai as genai`
    # We patch the module in sys.modules
    with patch.dict(sys.modules, {"google.generativeai": MagicMock()}):
        arch = Architect(api_key="AIzaSyD-12345678901234567890123456789012")
        assert arch.provider == "google"


@pytest.mark.asyncio
async def test_architect_detects_anthropic():
    # Patch the class in anthropic module
    with patch("anthropic.AsyncAnthropic"):
        arch = Architect(api_key="sk-ant-api03-12345")
        assert arch.provider == "anthropic"
        assert "claude" in arch.model


@pytest.mark.asyncio
async def test_consult_anthropic():
    # Mock the client class
    with patch("anthropic.AsyncAnthropic") as MockClientClass:
        mock_client = MockClientClass.return_value

        # Mock the response structure
        # response.content[0].text
        mock_message_response = MagicMock()
        mock_content_block = MagicMock()
        mock_content_block.text = '{"backlog": ["task1"]}'
        mock_message_response.content = [mock_content_block]

        mock_client.messages.create = AsyncMock(return_value=mock_message_response)

        arch = Architect(api_key="sk-ant-test")
        # Ensure provider is set
        # Since we patched AsyncAnthropic, the init should succeed and set provider

        result = await arch.consult({"thoughts": {}})

        assert result == '{"backlog": ["task1"]}'
        mock_client.messages.create.assert_called_once()
        _, kwargs = mock_client.messages.create.call_args
        assert (
            kwargs["system"]
            == "You are a precise technical architect. Output only valid JSON."
        )
