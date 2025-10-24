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
from typing import Any, Optional

from agdd.providers.base import LLMResponse


class GoogleSDKAdapter(ABC):
    """Abstract adapter interface for Google SDK implementations."""

    @abstractmethod
    def generate_content(self, prompt: str, **kwargs: Any) -> Any:
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

    @abstractmethod
    def extract_usage(self, response: Any) -> tuple[int, int]:
        """Extract token usage from SDK response.

        Args:
            response: Raw SDK response object

        Returns:
            Tuple of (input_tokens, output_tokens)

        Raises:
            Exception: If usage extraction fails
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
            import google.generativeai as genai
        except ImportError as e:
            raise ImportError(
                "google-generativeai package is required. "
                "Install with: pip install google-generativeai"
            ) from e

        genai.configure(api_key=api_key)  # type: ignore[attr-defined]
        self._model = genai.GenerativeModel(model_name)  # type: ignore[attr-defined]

    def generate_content(self, prompt: str, **kwargs: Any) -> Any:
        """Generate content using google-generativeai SDK.

        Args:
            prompt: The input prompt
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            GenerateContentResponse object
        """
        # google-generativeai uses synchronous generate_content
        response = self._model.generate_content(prompt, **kwargs)
        return response

    def extract_text(self, response: Any) -> str:
        """Extract text from GenerateContentResponse.

        Args:
            response: GenerateContentResponse object

        Returns:
            Generated text
        """
        return str(response.text)

    def extract_usage(self, response: Any) -> tuple[int, int]:
        """Extract token usage from GenerateContentResponse.

        Args:
            response: GenerateContentResponse object

        Returns:
            Tuple of (input_tokens, output_tokens)
        """
        # google-generativeai provides usage_metadata
        if hasattr(response, "usage_metadata"):
            usage = response.usage_metadata
            return (
                getattr(usage, "prompt_token_count", 0),
                getattr(usage, "candidates_token_count", 0),
            )
        return (0, 0)


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
            from google.genai import types
        except ImportError as e:
            raise ImportError(
                "google-genai package is required. "
                "Install with: pip install google-genai"
            ) from e

        self._client = genai.Client(api_key=api_key)
        self._model_name = model_name
        self._types = types

    def generate_content(self, prompt: str, **kwargs: Any) -> Any:
        """Generate content using google-genai SDK.

        Args:
            prompt: The input prompt
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            GenerateContentResponse object
        """
        # google-genai uses 'config' instead of 'generation_config'
        # Translate the parameter name if needed
        if "generation_config" in kwargs:
            kwargs["config"] = kwargs.pop("generation_config")

        # google-genai uses synchronous models.generate_content
        response = self._client.models.generate_content(
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
        # New SDK uses .output_text attribute
        return str(response.output_text)

    def extract_usage(self, response: Any) -> tuple[int, int]:
        """Extract token usage from GenerateContentResponse.

        Args:
            response: GenerateContentResponse object

        Returns:
            Tuple of (input_tokens, output_tokens)
        """
        # google-genai uses input_tokens and output_tokens
        if hasattr(response, "usage_metadata"):
            usage = response.usage_metadata
            return (
                getattr(usage, "input_tokens", 0),
                getattr(usage, "output_tokens", 0),
            )
        return (0, 0)


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


class GoogleProvider:
    """Google Generative AI provider with adapter pattern.

    This provider supports both google-generativeai (legacy) and google-genai (new)
    SDKs through an adapter pattern. The SDK can be selected via environment variable.

    Environment Variables:
        GOOGLE_SDK_TYPE: SDK to use (default: "google-generativeai")
        GOOGLE_API_KEY: Google API key (required)
        GOOGLE_MODEL_NAME: Model name (default: "gemini-1.5-pro")
    """

    # Cost per 1M tokens (USD) for Gemini models
    # Source: https://ai.google.dev/pricing
    COST_PER_1M_TOKENS = {
        "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
        "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
        "gemini-2.0-flash-exp": {"input": 0.0, "output": 0.0},  # Free tier
    }

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

        self._sdk_type: str = (
            sdk_type or os.getenv("GOOGLE_SDK_TYPE", "google-generativeai") or "google-generativeai"
        )

        self._model_name: str = (
            model_name or os.getenv("GOOGLE_MODEL_NAME", "gemini-1.5-pro") or "gemini-1.5-pro"
        )

        # Cache adapters by model name to allow per-request model selection
        self._adapters: dict[str, GoogleSDKAdapter] = {}

        # Create default adapter
        self._get_adapter(self._model_name)

    def _get_adapter(self, model: str) -> GoogleSDKAdapter:
        """Get or create an adapter for the specified model.

        Args:
            model: Model name

        Returns:
            GoogleSDKAdapter instance for the model
        """
        if model not in self._adapters:
            self._adapters[model] = create_google_adapter(
                sdk_type=self._sdk_type, api_key=self._api_key, model_name=model
            )
        return self._adapters[model]

    def generate(
        self,
        prompt: str,
        *,
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        tools: Optional[list[dict[str, Any]]] = None,
        tool_choice: Optional[str | dict[str, Any]] = None,
        response_format: Optional[dict[str, Any]] = None,
        reasoning: Optional[dict[str, Any]] = None,
        mcp_tools: Optional[list[dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate a completion from the LLM.

        Args:
            prompt: The input prompt/message.
            model: The model identifier to use.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature (0.0-2.0).
            tools: Tool definitions for function calling.
            tool_choice: Strategy for tool selection.
            response_format: Desired response format (e.g., JSON schema).
            reasoning: Reasoning configuration (e.g., extended thinking mode).
            mcp_tools: MCP (Model Context Protocol) tool definitions.
            **kwargs: Additional provider-specific parameters.

        Returns:
            LLMResponse containing the completion and metadata.
        """
        # Get adapter for the requested model
        adapter = self._get_adapter(model)

        # Build generation config
        generation_config = {
            "max_output_tokens": max_tokens,
            "temperature": temperature,
        }

        # Generate content using adapter
        response = adapter.generate_content(prompt, generation_config=generation_config, **kwargs)

        # Extract text and usage
        content = adapter.extract_text(response)
        input_tokens, output_tokens = adapter.extract_usage(response)

        return LLMResponse(
            content=content,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            metadata={
                "sdk_type": self._sdk_type,
                "raw_response": response,
            },
        )

    def get_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Calculate the cost for a completion.

        Args:
            model: The model identifier.
            input_tokens: Number of input tokens.
            output_tokens: Number of output tokens.

        Returns:
            Cost in USD.
        """
        # Get cost rates for the model
        cost_rates = self.COST_PER_1M_TOKENS.get(model)
        if not cost_rates:
            # Default to gemini-1.5-pro pricing if model not found
            cost_rates = self.COST_PER_1M_TOKENS["gemini-1.5-pro"]

        input_cost = (input_tokens / 1_000_000) * cost_rates["input"]
        output_cost = (output_tokens / 1_000_000) * cost_rates["output"]

        return input_cost + output_cost

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
