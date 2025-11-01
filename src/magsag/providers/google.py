"""Google Generative AI provider using the google-genai SDK.

This module provides a unified interface for Google's generative AI services
using the new google-genai SDK.

Environment Variables:
    GOOGLE_API_KEY: API key for Google's generative AI services
    GOOGLE_MODEL_NAME: Model name to use (e.g., "gemini-1.5-pro")
                       Default: "gemini-1.5-pro"
"""

import os
from typing import Any, Optional


from magsag.providers.base import LLMResponse


class GoogleProvider:
    """Google Generative AI provider using google-genai SDK.

    Environment Variables:
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
        model_name: str | None = None,
    ) -> None:
        """Initialize the Google provider.

        Args:
            api_key: Google API key (falls back to GOOGLE_API_KEY env var)
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

        self._model_name: str = (
            model_name or os.getenv("GOOGLE_MODEL_NAME", "gemini-1.5-pro") or "gemini-1.5-pro"
        )

        # Initialize google-genai SDK
        try:
            from google import genai
            from google.genai import types
        except ImportError as e:
            raise ImportError(
                "google-genai package is required. Install with: pip install google-genai"
            ) from e

        self._client = genai.Client(api_key=self._api_key)
        self._types = types

    def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate content using Google's generative AI models.

        Args:
            prompt: The input prompt
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens to generate
            model: Model to use (overrides default)
            **kwargs: Additional parameters for the API

        Returns:
            LLMResponse with generated content and metadata

        Raises:
            Exception: If generation fails
        """
        model_name = model or self._model_name

        # Prepare generation config
        config = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }

        # Add any extra kwargs to config
        config.update(kwargs)

        # Generate content
        response = self._client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=config,
        )

        # Extract text
        text = str(response.text)

        # Extract usage
        input_tokens = 0
        output_tokens = 0
        if hasattr(response, "usage_metadata"):
            usage = response.usage_metadata
            input_tokens = getattr(usage, "input_tokens", 0)
            output_tokens = getattr(usage, "output_tokens", 0)

        # Calculate costs
        model_costs = self.COST_PER_1M_TOKENS.get(model_name, {"input": 0.0, "output": 0.0})
        cost_usd = (
            input_tokens * model_costs["input"] / 1_000_000
            + output_tokens * model_costs["output"] / 1_000_000
        )

        return LLMResponse(
            content=text,
            model=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            metadata={
                "usage": {
                    "prompt_tokens": input_tokens,
                    "completion_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                },
                "cost_usd": cost_usd,
            },
        )

    async def agenerate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Async version of generate (currently wraps sync version).

        The google-genai SDK doesn't have native async support yet,
        so this wraps the synchronous call.

        Args:
            prompt: The input prompt
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens to generate
            model: Model to use (overrides default)
            **kwargs: Additional parameters for the API

        Returns:
            LLMResponse with generated content and metadata
        """
        # google-genai doesn't have async support yet, use sync
        return self.generate(
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
            **kwargs,
        )
