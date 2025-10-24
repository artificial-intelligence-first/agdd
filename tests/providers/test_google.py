"""Tests for Google Provider with adapter pattern."""

import os
from unittest.mock import MagicMock, patch

import pytest

from agdd.providers.google import (
    GoogleGenAIAdapter,
    GoogleGenerativeAIAdapter,
    GoogleProvider,
    create_google_adapter,
)


class TestGoogleGenerativeAIAdapter:
    """Tests for google-generativeai SDK adapter."""

    @pytest.fixture
    def mock_genai_module(self) -> MagicMock:
        """Mock google.generativeai module."""
        mock_genai = MagicMock()
        mock_model = MagicMock()

        # Mock response object
        mock_response = MagicMock()
        mock_response.text = "Generated text from legacy SDK"
        mock_usage = MagicMock()
        mock_usage.prompt_token_count = 10
        mock_usage.candidates_token_count = 20
        mock_response.usage_metadata = mock_usage

        # Mock method
        mock_model.generate_content = MagicMock(return_value=mock_response)
        mock_genai.GenerativeModel.return_value = mock_model

        return mock_genai

    def test_generate_content(self, mock_genai_module: MagicMock) -> None:
        """Test content generation with google-generativeai SDK."""
        mock_google = MagicMock()
        mock_google.generativeai = mock_genai_module
        with patch.dict(
            "sys.modules", {"google": mock_google, "google.generativeai": mock_genai_module}
        ):
            adapter = GoogleGenerativeAIAdapter(api_key="test-key", model_name="gemini-1.5-pro")

            response = adapter.generate_content("Test prompt")

            assert response.text == "Generated text from legacy SDK"
            mock_genai_module.configure.assert_called_once_with(api_key="test-key")
            mock_genai_module.GenerativeModel.assert_called_once_with("gemini-1.5-pro")

    def test_extract_text(self, mock_genai_module: MagicMock) -> None:
        """Test text extraction from response."""
        mock_google = MagicMock()
        mock_google.generativeai = mock_genai_module
        with patch.dict(
            "sys.modules", {"google": mock_google, "google.generativeai": mock_genai_module}
        ):
            adapter = GoogleGenerativeAIAdapter(api_key="test-key")

            response = adapter.generate_content("Test prompt")
            text = adapter.extract_text(response)

            assert text == "Generated text from legacy SDK"

    def test_extract_usage(self, mock_genai_module: MagicMock) -> None:
        """Test usage extraction from response."""
        mock_google = MagicMock()
        mock_google.generativeai = mock_genai_module
        with patch.dict(
            "sys.modules", {"google": mock_google, "google.generativeai": mock_genai_module}
        ):
            adapter = GoogleGenerativeAIAdapter(api_key="test-key")

            response = adapter.generate_content("Test prompt")
            input_tokens, output_tokens = adapter.extract_usage(response)

            assert input_tokens == 10
            assert output_tokens == 20

    def test_import_error(self) -> None:
        """Test that ImportError is raised when package is not installed."""
        with patch.dict("sys.modules", {"google.generativeai": None}):
            with pytest.raises(ImportError, match="google-generativeai package is required"):
                GoogleGenerativeAIAdapter(api_key="test-key")


class TestGoogleGenAIAdapter:
    """Tests for google-genai SDK adapter."""

    @pytest.fixture
    def mock_genai_module(self) -> tuple[MagicMock, MagicMock]:
        """Mock google.genai module."""
        mock_genai = MagicMock()
        mock_types = MagicMock()
        mock_client = MagicMock()

        # Mock response object
        mock_response = MagicMock()
        mock_response.output_text = "Generated text from new SDK"
        mock_usage = MagicMock()
        mock_usage.input_tokens = 15
        mock_usage.output_tokens = 25
        mock_response.usage_metadata = mock_usage

        # Mock method chain
        mock_client.models.generate_content = MagicMock(return_value=mock_response)
        mock_genai.Client.return_value = mock_client

        return mock_genai, mock_types

    def test_generate_content(self, mock_genai_module: tuple[MagicMock, MagicMock]) -> None:
        """Test content generation with google-genai SDK."""
        mock_genai, mock_types = mock_genai_module
        mock_google = MagicMock()
        mock_google.genai = mock_genai

        with patch.dict(
            "sys.modules",
            {"google": mock_google, "google.genai": mock_genai, "google.genai.types": mock_types},
        ):
            adapter = GoogleGenAIAdapter(api_key="test-key", model_name="gemini-1.5-pro")

            response = adapter.generate_content("Test prompt")

            assert response.output_text == "Generated text from new SDK"
            mock_genai.Client.assert_called_once_with(api_key="test-key")
            mock_genai.Client.return_value.models.generate_content.assert_called_once_with(
                model="gemini-1.5-pro", contents="Test prompt"
            )

    def test_generate_content_with_kwargs(
        self, mock_genai_module: tuple[MagicMock, MagicMock]
    ) -> None:
        """Test content generation with additional kwargs."""
        mock_genai, mock_types = mock_genai_module
        mock_google = MagicMock()
        mock_google.genai = mock_genai

        with patch.dict(
            "sys.modules",
            {"google": mock_google, "google.genai": mock_genai, "google.genai.types": mock_types},
        ):
            adapter = GoogleGenAIAdapter(api_key="test-key")

            # google-genai adapter translates generation_config to config
            adapter.generate_content(
                "Test prompt",
                generation_config={"temperature": 0.7, "max_output_tokens": 100},
            )

            # Verify that generation_config was translated to config
            mock_genai.Client.return_value.models.generate_content.assert_called_once_with(
                model="gemini-1.5-pro",
                contents="Test prompt",
                config={"temperature": 0.7, "max_output_tokens": 100},
            )

    def test_extract_text(self, mock_genai_module: tuple[MagicMock, MagicMock]) -> None:
        """Test text extraction from response."""
        mock_genai, mock_types = mock_genai_module
        mock_google = MagicMock()
        mock_google.genai = mock_genai

        with patch.dict(
            "sys.modules",
            {"google": mock_google, "google.genai": mock_genai, "google.genai.types": mock_types},
        ):
            adapter = GoogleGenAIAdapter(api_key="test-key")

            response = adapter.generate_content("Test prompt")
            text = adapter.extract_text(response)

            assert text == "Generated text from new SDK"

    def test_extract_usage(self, mock_genai_module: tuple[MagicMock, MagicMock]) -> None:
        """Test usage extraction from response."""
        mock_genai, mock_types = mock_genai_module
        mock_google = MagicMock()
        mock_google.genai = mock_genai

        with patch.dict(
            "sys.modules",
            {"google": mock_google, "google.genai": mock_genai, "google.genai.types": mock_types},
        ):
            adapter = GoogleGenAIAdapter(api_key="test-key")

            response = adapter.generate_content("Test prompt")
            input_tokens, output_tokens = adapter.extract_usage(response)

            assert input_tokens == 15
            assert output_tokens == 25

    def test_import_error(self) -> None:
        """Test that ImportError is raised when package is not installed."""
        with patch.dict("sys.modules", {"google.genai": None}):
            with pytest.raises(ImportError, match="google-genai package is required"):
                GoogleGenAIAdapter(api_key="test-key")


class TestCreateGoogleAdapter:
    """Tests for adapter factory function."""

    @patch("agdd.providers.google.GoogleGenerativeAIAdapter")
    def test_create_generativeai_adapter(self, mock_adapter_class: MagicMock) -> None:
        """Test factory creates google-generativeai adapter."""
        create_google_adapter("google-generativeai", "test-key", "gemini-1.5-pro")

        mock_adapter_class.assert_called_once_with(api_key="test-key", model_name="gemini-1.5-pro")

    @patch("agdd.providers.google.GoogleGenAIAdapter")
    def test_create_genai_adapter(self, mock_adapter_class: MagicMock) -> None:
        """Test factory creates google-genai adapter."""
        create_google_adapter("google-genai", "test-key", "gemini-1.5-pro")

        mock_adapter_class.assert_called_once_with(api_key="test-key", model_name="gemini-1.5-pro")

    def test_unknown_sdk_type(self) -> None:
        """Test factory raises error for unknown SDK type."""
        with pytest.raises(ValueError, match="Unknown SDK type: unknown-sdk"):
            create_google_adapter("unknown-sdk", "test-key")


class TestGoogleProvider:
    """Tests for GoogleProvider class."""

    @pytest.fixture
    def mock_adapter(self) -> MagicMock:
        """Mock GoogleSDKAdapter."""
        adapter = MagicMock()
        mock_response = MagicMock()
        adapter.generate_content = MagicMock(return_value=mock_response)
        adapter.extract_text = MagicMock(return_value="Test response")
        adapter.extract_usage = MagicMock(return_value=(10, 20))
        return adapter

    @patch("agdd.providers.google.create_google_adapter")
    def test_init_with_api_key(self, mock_factory: MagicMock, mock_adapter: MagicMock) -> None:
        """Test provider initialization with API key."""
        mock_factory.return_value = mock_adapter

        provider = GoogleProvider(api_key="test-key")

        assert provider.sdk_type == "google-generativeai"
        assert provider.model_name == "gemini-1.5-pro"
        mock_factory.assert_called_once_with(
            sdk_type="google-generativeai", api_key="test-key", model_name="gemini-1.5-pro"
        )

    @patch("agdd.providers.google.create_google_adapter")
    def test_init_with_env_var(self, mock_factory: MagicMock, mock_adapter: MagicMock) -> None:
        """Test provider initialization with environment variables."""
        mock_factory.return_value = mock_adapter

        with patch.dict(
            os.environ,
            {
                "GOOGLE_API_KEY": "env-api-key",
                "GOOGLE_SDK_TYPE": "google-genai",
                "GOOGLE_MODEL_NAME": "gemini-2.0-flash",
            },
        ):
            provider = GoogleProvider()

            assert provider.sdk_type == "google-genai"
            assert provider.model_name == "gemini-2.0-flash"
            mock_factory.assert_called_once_with(
                sdk_type="google-genai", api_key="env-api-key", model_name="gemini-2.0-flash"
            )

    @patch("agdd.providers.google.create_google_adapter")
    def test_init_param_overrides_env(
        self, mock_factory: MagicMock, mock_adapter: MagicMock
    ) -> None:
        """Test that parameters override environment variables."""
        mock_factory.return_value = mock_adapter

        with patch.dict(
            os.environ,
            {
                "GOOGLE_API_KEY": "env-api-key",
                "GOOGLE_SDK_TYPE": "google-genai",
            },
        ):
            provider = GoogleProvider(api_key="param-api-key", sdk_type="google-generativeai")

            assert provider.sdk_type == "google-generativeai"
            mock_factory.assert_called_once_with(
                sdk_type="google-generativeai",
                api_key="param-api-key",
                model_name="gemini-1.5-pro",
            )

    def test_init_without_api_key(self) -> None:
        """Test that ValueError is raised when API key is missing."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="Google API key is required"):
                GoogleProvider()

    @patch("agdd.providers.google.create_google_adapter")
    def test_generate(self, mock_factory: MagicMock, mock_adapter: MagicMock) -> None:
        """Test generate method."""
        mock_factory.return_value = mock_adapter

        provider = GoogleProvider(api_key="test-key")
        result = provider.generate("Test prompt", model="gemini-1.5-pro")

        assert result.content == "Test response"
        assert result.model == "gemini-1.5-pro"
        assert result.input_tokens == 10
        assert result.output_tokens == 20
        assert result.metadata["sdk_type"] == "google-generativeai"
        # Should be called once for default model in __init__
        assert mock_factory.call_count >= 1
        mock_adapter.generate_content.assert_called_once()

    @patch("agdd.providers.google.create_google_adapter")
    def test_generate_with_kwargs(
        self, mock_factory: MagicMock, mock_adapter: MagicMock
    ) -> None:
        """Test generate method with additional kwargs."""
        mock_factory.return_value = mock_adapter

        provider = GoogleProvider(api_key="test-key")
        provider.generate("Test prompt", model="gemini-1.5-pro", max_tokens=500, temperature=0.8)

        # Verify generation_config was passed correctly
        call_args = mock_adapter.generate_content.call_args
        assert call_args[1]["generation_config"]["max_output_tokens"] == 500
        assert call_args[1]["generation_config"]["temperature"] == 0.8

    @patch("agdd.providers.google.create_google_adapter")
    def test_get_cost(self, mock_factory: MagicMock, mock_adapter: MagicMock) -> None:
        """Test get_cost method."""
        mock_factory.return_value = mock_adapter

        provider = GoogleProvider(api_key="test-key")
        cost = provider.get_cost("gemini-1.5-pro", 1_000_000, 1_000_000)

        # 1M input tokens * $1.25 + 1M output tokens * $5.00 = $6.25
        assert cost == 6.25

    @patch("agdd.providers.google.create_google_adapter")
    def test_get_cost_unknown_model(
        self, mock_factory: MagicMock, mock_adapter: MagicMock
    ) -> None:
        """Test get_cost with unknown model defaults to gemini-1.5-pro pricing."""
        mock_factory.return_value = mock_adapter

        provider = GoogleProvider(api_key="test-key")
        cost = provider.get_cost("unknown-model", 1_000_000, 1_000_000)

        # Should use default gemini-1.5-pro pricing
        assert cost == 6.25

    @patch("agdd.providers.google.create_google_adapter")
    def test_sdk_switching(
        self,
        mock_factory: MagicMock,
    ) -> None:
        """Test that different SDK types can be used."""
        mock_adapter_legacy = MagicMock()
        mock_adapter_new = MagicMock()

        # Test with legacy SDK
        mock_factory.return_value = mock_adapter_legacy
        provider_legacy = GoogleProvider(api_key="test-key", sdk_type="google-generativeai")
        assert provider_legacy.sdk_type == "google-generativeai"

        # Test with new SDK
        mock_factory.return_value = mock_adapter_new
        provider_new = GoogleProvider(api_key="test-key", sdk_type="google-genai")
        assert provider_new.sdk_type == "google-genai"

    @patch("agdd.providers.google.create_google_adapter")
    def test_per_request_model_selection(
        self, mock_factory: MagicMock, mock_adapter: MagicMock
    ) -> None:
        """Test that different models can be used per request."""
        mock_adapter_pro = MagicMock()
        mock_adapter_pro.generate_content = MagicMock(return_value=MagicMock())
        mock_adapter_pro.extract_text = MagicMock(return_value="Pro response")
        mock_adapter_pro.extract_usage = MagicMock(return_value=(10, 20))

        mock_adapter_flash = MagicMock()
        mock_adapter_flash.generate_content = MagicMock(return_value=MagicMock())
        mock_adapter_flash.extract_text = MagicMock(return_value="Flash response")
        mock_adapter_flash.extract_usage = MagicMock(return_value=(5, 10))

        def adapter_factory(sdk_type: str, api_key: str, model_name: str) -> MagicMock:
            if model_name == "gemini-1.5-pro":
                return mock_adapter_pro
            elif model_name == "gemini-1.5-flash":
                return mock_adapter_flash
            return mock_adapter_pro

        mock_factory.side_effect = adapter_factory

        provider = GoogleProvider(api_key="test-key")

        # Use gemini-1.5-pro
        result_pro = provider.generate("Test prompt", model="gemini-1.5-pro")
        assert result_pro.model == "gemini-1.5-pro"
        assert result_pro.content == "Pro response"

        # Use gemini-1.5-flash
        result_flash = provider.generate("Test prompt", model="gemini-1.5-flash")
        assert result_flash.model == "gemini-1.5-flash"
        assert result_flash.content == "Flash response"

        # Verify adapters were created for both models
        assert mock_factory.call_count == 2

    @patch("agdd.providers.google.create_google_adapter")
    def test_adapter_caching(self, mock_factory: MagicMock, mock_adapter: MagicMock) -> None:
        """Test that adapters are cached and reused."""
        mock_factory.return_value = mock_adapter

        provider = GoogleProvider(api_key="test-key")

        # Call generate with same model multiple times
        provider.generate("Test 1", model="gemini-1.5-pro")
        provider.generate("Test 2", model="gemini-1.5-pro")
        provider.generate("Test 3", model="gemini-1.5-pro")

        # Adapter should only be created once (during __init__)
        assert mock_factory.call_count == 1
