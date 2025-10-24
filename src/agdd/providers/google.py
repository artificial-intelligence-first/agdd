"""Google Generative AI provider with adapter pattern for SDK switching.

This module provides a unified interface for Google's generative AI services,
supporting both the legacy google-generativeai SDK and the new google-genai SDK.
The implementation uses the Adapter pattern to allow runtime switching between SDKs.

Environment Variables:
    GOOGLE_SDK_TYPE: SDK to use ("google-generativeai" or "google-genai")
                     Default: "google-generativeai"
    GOOGLE_API_KEY: API key for Google's generative AI services
    GOOGLE_MODEL_NAME: Model name to use (e.g., "gemini-1.5-pro")
                       Default: "gemini-1.5-pro"
"""

import os
from abc import ABC, abstractmethod
from typing import Any

from agdd.providers.base import BaseProvider


class GoogleSDKAdapter(ABC):
    """Abstract adapter interface for Google SDK implementations."""

    @abstractmethod
    async def generate_content(self, prompt: str, **kwargs: Any) -> Any:
        """Generate content using the SDK.

        Args:
            prompt: The input prompt
            **kwargs: Additional SDK-specific parameters

        Returns:
            Raw SDK response object

        Raises:
            Exception: If content generation fails
        """
        pass

    @abstractmethod
    def extract_text(self, response: Any) -> str:
        """Extract text from SDK response.

        Args:
            response: Raw SDK response object

        Returns:
            Generated text content

        Raises:
            Exception: If text extraction fails
        """
        pass


class GoogleGenerativeAIAdapter(GoogleSDKAdapter):
    """Adapter for google-generativeai SDK (legacy)."""

    def __init__(self, api_key: str, model_name: str = "gemini-1.5-pro") -> None:
        """Initialize the adapter.

        Args:
            api_key: Google API key
            model_name: Model name to use
        """
        try:
            import google.generativeai as genai  # type: ignore[import-not-found]
        except ImportError as e:
            raise ImportError(
                "google-generativeai package is required. "
                "Install with: pip install google-generativeai"
            ) from e

        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model_name)

    async def generate_content(self, prompt: str, **kwargs: Any) -> Any:
        """Generate content using google-generativeai SDK.

        Args:
            prompt: The input prompt
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            GenerateContentResponse object
        """
        # google-generativeai uses generate_content_async for async
        response = await self._model.generate_content_async(prompt, **kwargs)
        return response

    def extract_text(self, response: Any) -> str:
        """Extract text from GenerateContentResponse.

        Args:
            response: GenerateContentResponse object

        Returns:
            Generated text
        """
        return str(response.text)


class GoogleGenAIAdapter(GoogleSDKAdapter):
    """Adapter for google-genai SDK (new)."""

    def __init__(self, api_key: str, model_name: str = "gemini-1.5-pro") -> None:
        """Initialize the adapter.

        Args:
            api_key: Google API key
            model_name: Model name to use
        """
        try:
            from google import genai
            from google.genai import types  # type: ignore[import-not-found]
        except ImportError as e:
            raise ImportError(
                "google-genai package is required. "
                "Install with: pip install google-genai"
            ) from e

        self._client = genai.Client(api_key=api_key)
        self._model_name = model_name
        self._types = types

    async def generate_content(self, prompt: str, **kwargs: Any) -> Any:
        """Generate content using google-genai SDK.

        Args:
            prompt: The input prompt
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            GenerateContentResponse object
        """
        # google-genai uses aio for async operations
        response = await self._client.aio.models.generate_content(
            model=self._model_name, contents=prompt, **kwargs
        )
        return response

    def extract_text(self, response: Any) -> str:
        """Extract text from GenerateContentResponse.

        Args:
            response: GenerateContentResponse object

        Returns:
            Generated text
        """
        # New SDK uses .text attribute
        return str(response.text)


def create_google_adapter(
    sdk_type: str, api_key: str, model_name: str = "gemini-1.5-pro"
) -> GoogleSDKAdapter:
    """Factory function to create appropriate Google SDK adapter.

    Args:
        sdk_type: Type of SDK ("google-generativeai" or "google-genai")
        api_key: Google API key
        model_name: Model name to use

    Returns:
        Appropriate GoogleSDKAdapter implementation

    Raises:
        ValueError: If sdk_type is not recognized
    """
    if sdk_type == "google-generativeai":
        return GoogleGenerativeAIAdapter(api_key=api_key, model_name=model_name)
    elif sdk_type == "google-genai":
        return GoogleGenAIAdapter(api_key=api_key, model_name=model_name)
    else:
        raise ValueError(
            f"Unknown SDK type: {sdk_type}. "
            f"Must be 'google-generativeai' or 'google-genai'"
        )


class GoogleProvider(BaseProvider):
    """Google Generative AI provider with adapter pattern.

    This provider supports both google-generativeai (legacy) and google-genai (new)
    SDKs through an adapter pattern. The SDK can be selected via environment variable.

    Environment Variables:
        GOOGLE_SDK_TYPE: SDK to use (default: "google-generativeai")
        GOOGLE_API_KEY: Google API key (required)
        GOOGLE_MODEL_NAME: Model name (default: "gemini-1.5-pro")
    """

    def __init__(
        self,
        api_key: str | None = None,
        sdk_type: str | None = None,
        model_name: str | None = None,
    ) -> None:
        """Initialize the Google provider.

        Args:
            api_key: Google API key (falls back to GOOGLE_API_KEY env var)
            sdk_type: SDK type (falls back to GOOGLE_SDK_TYPE env var)
            model_name: Model name (falls back to GOOGLE_MODEL_NAME env var)

        Raises:
            ValueError: If api_key is not provided
        """
        resolved_api_key: str = api_key or os.getenv("GOOGLE_API_KEY") or ""
        if not resolved_api_key:
            raise ValueError(
                "Google API key is required. "
                "Set GOOGLE_API_KEY environment variable or pass api_key parameter."
            )
        self._api_key: str = resolved_api_key

        self._sdk_type: str = sdk_type or os.getenv(
            "GOOGLE_SDK_TYPE", "google-generativeai"
        ) or "google-generativeai"

        self._model_name: str = model_name or os.getenv(
            "GOOGLE_MODEL_NAME", "gemini-1.5-pro"
        ) or "gemini-1.5-pro"

        # Create adapter using factory
        self._adapter = create_google_adapter(
            sdk_type=self._sdk_type, api_key=self._api_key, model_name=self._model_name
        )

    async def invoke(self, prompt: str, **kwargs: Any) -> str:
        """Invoke the LLM with a prompt and return the response text.

        Args:
            prompt: The input prompt to send to the LLM
            **kwargs: Additional provider-specific parameters

        Returns:
            The generated text response from the LLM

        Raises:
            Exception: If the invocation fails
        """
        response = await self.generate_content_async(prompt, **kwargs)
        return self._adapter.extract_text(response)

    async def generate_content_async(self, prompt: str, **kwargs: Any) -> Any:
        """Generate content asynchronously using the provider's SDK.

        Args:
            prompt: The input prompt to send to the LLM
            **kwargs: Additional provider-specific parameters

        Returns:
            The raw response object from the provider's SDK

        Raises:
            Exception: If content generation fails
        """
        return await self._adapter.generate_content(prompt, **kwargs)

    @property
    def sdk_type(self) -> str:
        """Get the current SDK type being used.

        Returns:
            SDK type string ("google-generativeai" or "google-genai")
        """
        return self._sdk_type

    @property
    def model_name(self) -> str:
        """Get the current model name being used.

        Returns:
            Model name string
        """
        return self._model_name
