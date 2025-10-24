"""Abstract base class for LLM providers."""

from abc import ABC, abstractmethod
from typing import Any


class BaseProvider(ABC):
    """Abstract base class for LLM provider implementations.

    All provider adapters must implement this interface to ensure
    consistent behavior across different LLM services.
    """

    @abstractmethod
    async def invoke(self, prompt: str, **kwargs: Any) -> str:
        """Invoke the LLM with a prompt and return the response.

        Args:
            prompt: The input prompt to send to the LLM
            **kwargs: Additional provider-specific parameters

        Returns:
            The generated text response from the LLM

        Raises:
            Exception: If the invocation fails
        """
        pass

    @abstractmethod
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
        pass
