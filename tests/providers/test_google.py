"""Tests for Google Provider using google-genai SDK."""

import os
from unittest.mock import MagicMock, patch

import pytest

from agdd.providers.google import GoogleProvider


class TestGoogleProvider:
    """Tests for GoogleProvider class."""

    @pytest.fixture
    def mock_genai_modules(self) -> tuple[MagicMock, MagicMock]:
        """Mock google.genai module."""
        mock_genai = MagicMock()
        mock_types = MagicMock()
        mock_client = MagicMock()

        # Mock response object
        mock_response = MagicMock()
        mock_response.text = "Generated text from google-genai SDK"
        mock_usage = MagicMock()
        mock_usage.input_tokens = 10
        mock_usage.output_tokens = 20
        mock_response.usage_metadata = mock_usage

        # Mock method chain
        mock_client.models.generate_content = MagicMock(return_value=mock_response)
        mock_genai.Client.return_value = mock_client

        return mock_genai, mock_types

    def test_init_with_api_key(self, mock_genai_modules: tuple[MagicMock, MagicMock]) -> None:
        """Test provider initialization with API key."""
        mock_genai, mock_types = mock_genai_modules
        mock_google = MagicMock()
        mock_google.genai = mock_genai

        with patch.dict(
            "sys.modules",
            {"google": mock_google, "google.genai": mock_genai, "google.genai.types": mock_types},
        ):
            provider = GoogleProvider(api_key="test-key")

            assert provider._api_key == "test-key"
            assert provider._model_name == "gemini-1.5-pro"
            mock_genai.Client.assert_called_once_with(api_key="test-key")

    def test_init_with_env_var(self, mock_genai_modules: tuple[MagicMock, MagicMock]) -> None:
        """Test provider initialization with environment variables."""
        mock_genai, mock_types = mock_genai_modules
        mock_google = MagicMock()
        mock_google.genai = mock_genai

        with patch.dict(
            os.environ,
            {
                "GOOGLE_API_KEY": "env-api-key",
                "GOOGLE_MODEL_NAME": "gemini-2.0-flash-exp",
            },
        ):
            with patch.dict(
                "sys.modules",
                {
                    "google": mock_google,
                    "google.genai": mock_genai,
                    "google.genai.types": mock_types,
                },
            ):
                provider = GoogleProvider()

                assert provider._api_key == "env-api-key"
                assert provider._model_name == "gemini-2.0-flash-exp"

    def test_init_param_overrides_env(
        self, mock_genai_modules: tuple[MagicMock, MagicMock]
    ) -> None:
        """Test that parameters override environment variables."""
        mock_genai, mock_types = mock_genai_modules
        mock_google = MagicMock()
        mock_google.genai = mock_genai

        with patch.dict(
            os.environ,
            {
                "GOOGLE_API_KEY": "env-api-key",
                "GOOGLE_MODEL_NAME": "gemini-1.5-flash",
            },
        ):
            with patch.dict(
                "sys.modules",
                {
                    "google": mock_google,
                    "google.genai": mock_genai,
                    "google.genai.types": mock_types,
                },
            ):
                provider = GoogleProvider(api_key="param-api-key", model_name="gemini-1.5-pro")

                assert provider._api_key == "param-api-key"
                assert provider._model_name == "gemini-1.5-pro"

    def test_init_without_api_key(self) -> None:
        """Test that ValueError is raised when API key is missing."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="Google API key is required"):
                GoogleProvider()

    def test_generate(self, mock_genai_modules: tuple[MagicMock, MagicMock]) -> None:
        """Test generate method."""
        mock_genai, mock_types = mock_genai_modules
        mock_google = MagicMock()
        mock_google.genai = mock_genai

        with patch.dict(
            "sys.modules",
            {"google": mock_google, "google.genai": mock_genai, "google.genai.types": mock_types},
        ):
            provider = GoogleProvider(api_key="test-key")
            result = provider.generate("Test prompt")

            assert result.content == "Generated text from google-genai SDK"
            assert result.model == "gemini-1.5-pro"
            assert result.input_tokens == 10
            assert result.output_tokens == 20
            assert "cost_usd" in result.metadata

    def test_generate_with_custom_model(
        self, mock_genai_modules: tuple[MagicMock, MagicMock]
    ) -> None:
        """Test generate method with custom model."""
        mock_genai, mock_types = mock_genai_modules
        mock_google = MagicMock()
        mock_google.genai = mock_genai

        with patch.dict(
            "sys.modules",
            {"google": mock_google, "google.genai": mock_genai, "google.genai.types": mock_types},
        ):
            provider = GoogleProvider(api_key="test-key")
            result = provider.generate("Test prompt", model="gemini-1.5-flash")

            assert result.model == "gemini-1.5-flash"
            mock_client = mock_genai.Client.return_value
            mock_client.models.generate_content.assert_called_once()
            call_args = mock_client.models.generate_content.call_args
            assert call_args[1]["model"] == "gemini-1.5-flash"

    def test_generate_with_kwargs(self, mock_genai_modules: tuple[MagicMock, MagicMock]) -> None:
        """Test generate method with additional kwargs."""
        mock_genai, mock_types = mock_genai_modules
        mock_google = MagicMock()
        mock_google.genai = mock_genai

        with patch.dict(
            "sys.modules",
            {"google": mock_google, "google.genai": mock_genai, "google.genai.types": mock_types},
        ):
            provider = GoogleProvider(api_key="test-key")
            provider.generate("Test prompt", temperature=0.9, max_tokens=500)

            mock_client = mock_genai.Client.return_value
            call_args = mock_client.models.generate_content.call_args
            config = call_args[1]["config"]
            assert config["temperature"] == 0.9
            assert config["max_output_tokens"] == 500

    def test_agenerate(self, mock_genai_modules: tuple[MagicMock, MagicMock]) -> None:
        """Test async generate method (currently wraps sync)."""
        mock_genai, mock_types = mock_genai_modules
        mock_google = MagicMock()
        mock_google.genai = mock_genai

        with patch.dict(
            "sys.modules",
            {"google": mock_google, "google.genai": mock_genai, "google.genai.types": mock_types},
        ):
            provider = GoogleProvider(api_key="test-key")

            # agenerate currently wraps sync generate
            import asyncio

            result = asyncio.run(provider.agenerate("Test prompt"))

            assert result.content == "Generated text from google-genai SDK"
            assert result.model == "gemini-1.5-pro"

    def test_cost_calculation(self, mock_genai_modules: tuple[MagicMock, MagicMock]) -> None:
        """Test cost calculation for different models."""
        mock_genai, mock_types = mock_genai_modules
        mock_google = MagicMock()
        mock_google.genai = mock_genai

        with patch.dict(
            "sys.modules",
            {"google": mock_google, "google.genai": mock_genai, "google.genai.types": mock_types},
        ):
            provider = GoogleProvider(api_key="test-key")
            result = provider.generate("Test prompt")

            # For gemini-1.5-pro: 10 input tokens * $1.25/1M + 20 output tokens * $5.00/1M
            expected_cost = (10 * 1.25 + 20 * 5.00) / 1_000_000
            assert result.metadata["cost_usd"] == pytest.approx(expected_cost)

    def test_import_error(self) -> None:
        """Test that ImportError is raised when google-genai is not installed."""
        with patch.dict("sys.modules", {"google.genai": None}):
            with pytest.raises(ImportError, match="google-genai package is required"):
                GoogleProvider(api_key="test-key")
