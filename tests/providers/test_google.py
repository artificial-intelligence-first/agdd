"""Tests for Google Provider with adapter pattern."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

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

        # Mock async method
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_genai.GenerativeModel.return_value = mock_model

        return mock_genai

    @pytest.mark.asyncio
    async def test_generate_content(self, mock_genai_module: MagicMock) -> None:
        """Test content generation with google-generativeai SDK."""
        mock_google = MagicMock()
        mock_google.generativeai = mock_genai_module
        with patch.dict("sys.modules", {"google": mock_google, "google.generativeai": mock_genai_module}):
            adapter = GoogleGenerativeAIAdapter(api_key="test-key", model_name="gemini-1.5-pro")

            response = await adapter.generate_content("Test prompt")

            assert response.text == "Generated text from legacy SDK"
            mock_genai_module.configure.assert_called_once_with(api_key="test-key")
            mock_genai_module.GenerativeModel.assert_called_once_with("gemini-1.5-pro")

    @pytest.mark.asyncio
    async def test_extract_text(self, mock_genai_module: MagicMock) -> None:
        """Test text extraction from response."""
        mock_google = MagicMock()
        mock_google.generativeai = mock_genai_module
        with patch.dict("sys.modules", {"google": mock_google, "google.generativeai": mock_genai_module}):
            adapter = GoogleGenerativeAIAdapter(api_key="test-key")

            response = await adapter.generate_content("Test prompt")
            text = adapter.extract_text(response)

            assert text == "Generated text from legacy SDK"

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
        mock_response.text = "Generated text from new SDK"

        # Mock async method chain
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
        mock_genai.Client.return_value = mock_client

        return mock_genai, mock_types

    @pytest.mark.asyncio
    async def test_generate_content(
        self, mock_genai_module: tuple[MagicMock, MagicMock]
    ) -> None:
        """Test content generation with google-genai SDK."""
        mock_genai, mock_types = mock_genai_module
        mock_google = MagicMock()
        mock_google.genai = mock_genai

        with patch.dict(
            "sys.modules",
            {"google": mock_google, "google.genai": mock_genai, "google.genai.types": mock_types},
        ):
            adapter = GoogleGenAIAdapter(api_key="test-key", model_name="gemini-1.5-pro")

            response = await adapter.generate_content("Test prompt")

            assert response.text == "Generated text from new SDK"
            mock_genai.Client.assert_called_once_with(api_key="test-key")
            mock_genai.Client.return_value.aio.models.generate_content.assert_called_once_with(
                model="gemini-1.5-pro", contents="Test prompt"
            )

    @pytest.mark.asyncio
    async def test_generate_content_with_kwargs(
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

            await adapter.generate_content("Test prompt", temperature=0.7, max_tokens=100)

            mock_genai.Client.return_value.aio.models.generate_content.assert_called_once_with(
                model="gemini-1.5-pro",
                contents="Test prompt",
                temperature=0.7,
                max_tokens=100,
            )

    @pytest.mark.asyncio
    async def test_extract_text(
        self, mock_genai_module: tuple[MagicMock, MagicMock]
    ) -> None:
        """Test text extraction from response."""
        mock_genai, mock_types = mock_genai_module
        mock_google = MagicMock()
        mock_google.genai = mock_genai

        with patch.dict(
            "sys.modules",
            {"google": mock_google, "google.genai": mock_genai, "google.genai.types": mock_types},
        ):
            adapter = GoogleGenAIAdapter(api_key="test-key")

            response = await adapter.generate_content("Test prompt")
            text = adapter.extract_text(response)

            assert text == "Generated text from new SDK"

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

        mock_adapter_class.assert_called_once_with(
            api_key="test-key", model_name="gemini-1.5-pro"
        )

    @patch("agdd.providers.google.GoogleGenAIAdapter")
    def test_create_genai_adapter(self, mock_adapter_class: MagicMock) -> None:
        """Test factory creates google-genai adapter."""
        create_google_adapter("google-genai", "test-key", "gemini-1.5-pro")

        mock_adapter_class.assert_called_once_with(
            api_key="test-key", model_name="gemini-1.5-pro"
        )

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
        adapter.generate_content = AsyncMock(return_value=MagicMock(text="Test response"))
        adapter.extract_text = MagicMock(return_value="Test response")
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

    @pytest.mark.asyncio
    @patch("agdd.providers.google.create_google_adapter")
    async def test_invoke(self, mock_factory: MagicMock, mock_adapter: MagicMock) -> None:
        """Test invoke method."""
        mock_factory.return_value = mock_adapter

        provider = GoogleProvider(api_key="test-key")
        result = await provider.invoke("Test prompt")

        assert result == "Test response"
        mock_adapter.generate_content.assert_called_once_with("Test prompt")
        mock_adapter.extract_text.assert_called_once()

    @pytest.mark.asyncio
    @patch("agdd.providers.google.create_google_adapter")
    async def test_invoke_with_kwargs(
        self, mock_factory: MagicMock, mock_adapter: MagicMock
    ) -> None:
        """Test invoke method with additional kwargs."""
        mock_factory.return_value = mock_adapter

        provider = GoogleProvider(api_key="test-key")
        await provider.invoke("Test prompt", temperature=0.8, max_tokens=200)

        mock_adapter.generate_content.assert_called_once_with(
            "Test prompt", temperature=0.8, max_tokens=200
        )

    @pytest.mark.asyncio
    @patch("agdd.providers.google.create_google_adapter")
    async def test_generate_content_async(
        self, mock_factory: MagicMock, mock_adapter: MagicMock
    ) -> None:
        """Test generate_content_async method."""
        mock_response = MagicMock()
        mock_adapter.generate_content = AsyncMock(return_value=mock_response)
        mock_factory.return_value = mock_adapter

        provider = GoogleProvider(api_key="test-key")
        response = await provider.generate_content_async("Test prompt")

        assert response == mock_response
        mock_adapter.generate_content.assert_called_once_with("Test prompt")

    @pytest.mark.asyncio
    @patch("agdd.providers.google.create_google_adapter")
    async def test_sdk_switching(
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
