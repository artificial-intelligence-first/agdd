"""Base classes and protocols for skill development with MCP support.

This module provides the foundational building blocks for creating skills
in the AGDD framework, including:
- Legacy synchronous Skill protocol (Phase 1)
- Modern asynchronous MCPSkill protocol with MCP support (Phase 2+)
- SkillBase helper class with validation and MCP utilities

Example usage for Phase 1 (legacy sync):
    ```python
    from agdd.skills.base import Skill

    class EchoSkill:
        def __call__(self, text: str) -> str:
            return text
    ```

Example usage for Phase 2+ (async with MCP):
    ```python
    from agdd.skills.base import MCPSkill, SkillBase
    from agdd.mcp import MCPRuntime

    class WebSearchSkill:
        async def execute(
            self,
            payload: dict[str, Any],
            mcp_runtime: MCPRuntime
        ) -> dict[str, Any]:
            # Validate input
            SkillBase.validate_payload(payload, input_schema)

            # Use MCP runtime to access tools
            result = await mcp_runtime.execute_tool(
                server_id="fetch",
                tool_name="get",
                arguments={"url": payload["url"]}
            )

            return {"content": result.output}
    ```
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

import jsonschema

from agdd.mcp import MCPRuntime

logger = logging.getLogger(__name__)


class SkillValidationError(Exception):
    """Exception raised when skill input or output validation fails."""

    pass


class SkillMCPError(Exception):
    """Exception raised when MCP runtime is not available or misconfigured."""

    pass


@runtime_checkable
class Skill(Protocol):
    """Protocol for Phase 1 legacy synchronous skills.

    This is the original skill interface for simple text-in/text-out
    transformations. For new skills with MCP integration, use MCPSkill instead.

    Example:
        ```python
        class EchoSkill:
            def __call__(self, text: str) -> str:
                return text
        ```
    """

    def __call__(self, text: str) -> str:  # pragma: no cover - interface contract
        """Execute the skill with text input.

        Args:
            text: Input text to process

        Returns:
            Processed output text
        """
        ...


@runtime_checkable
class MCPSkill(Protocol):
    """Protocol for Phase 2+ asynchronous skills with MCP support.

    This modern skill interface supports structured payloads and
    MCP runtime access for enhanced capabilities like database queries,
    API calls, and external tool integration.

    Skills implementing this protocol should:
    1. Accept structured data as dict payload
    2. Receive MCPRuntime for tool access
    3. Return structured dict results
    4. Use async/await for I/O operations

    Example:
        ```python
        class DatabaseQuerySkill:
            async def execute(
                self,
                payload: dict[str, Any],
                mcp_runtime: MCPRuntime
            ) -> dict[str, Any]:
                result = await mcp_runtime.query_postgres(
                    server_id="pg-readonly",
                    sql=payload["query"]
                )
                return {"rows": result.output}
        ```
    """

    async def execute(
        self,
        payload: dict[str, Any],
        mcp_runtime: MCPRuntime,
    ) -> dict[str, Any]:  # pragma: no cover - interface contract
        """Execute the skill with structured input and MCP runtime.

        Args:
            payload: Structured input data (validated against skill's input schema)
            mcp_runtime: MCP runtime for accessing external tools and services

        Returns:
            Structured output data (should conform to skill's output schema)

        Raises:
            SkillValidationError: If payload validation fails
            SkillMCPError: If MCP runtime access fails
        """
        ...


class SkillBase:
    """Helper class providing common utilities for skill development.

    This class offers static methods for:
    - JSON Schema validation of inputs/outputs
    - MCP runtime availability checks
    - Consistent error messaging

    This is not meant to be instantiated or subclassed directly.
    Use the static methods as needed in your skill implementations.

    Example:
        ```python
        class MySkill:
            async def execute(
                self,
                payload: dict[str, Any],
                mcp_runtime: MCPRuntime
            ) -> dict[str, Any]:
                # Validate input
                SkillBase.validate_payload(payload, MY_INPUT_SCHEMA)

                # Ensure MCP is available
                SkillBase.requires_mcp(mcp_runtime, "pg-readonly")

                # Process...
                result = await mcp_runtime.execute_tool(...)

                # Validate output
                output = {"result": result.output}
                SkillBase.validate_payload(output, MY_OUTPUT_SCHEMA)
                return output
        ```
    """

    @staticmethod
    def validate_payload(
        payload: dict[str, Any],
        schema: dict[str, Any],
        payload_name: str = "payload",
    ) -> None:
        """Validate a payload against a JSON Schema.

        Args:
            payload: Data to validate
            schema: JSON Schema definition (must be a valid JSON Schema object)
            payload_name: Human-readable name for error messages (default: "payload")

        Raises:
            SkillValidationError: If validation fails with details about the error

        Example:
            ```python
            schema = {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "extract_text": {"type": "boolean"}
                },
                "required": ["url"]
            }

            SkillBase.validate_payload(
                payload={"url": "https://example.com"},
                schema=schema,
                payload_name="web_search_input"
            )
            ```
        """
        try:
            jsonschema.validate(payload, schema)
        except jsonschema.ValidationError as exc:
            error_msg = f"{payload_name} schema validation failed: {exc.message}"
            logger.error(f"{error_msg} at path: {list(exc.path)}")
            raise SkillValidationError(error_msg) from exc
        except jsonschema.SchemaError as exc:
            error_msg = f"Invalid JSON Schema for {payload_name}: {exc.message}"
            logger.error(error_msg)
            raise SkillValidationError(error_msg) from exc

    @staticmethod
    def requires_mcp(
        mcp_runtime: MCPRuntime | None,
        server_id: str | None = None,
    ) -> None:
        """Ensure MCP runtime is available and properly configured.

        This method validates that:
        1. MCP runtime is provided (not None)
        2. If server_id is specified, runtime has permission to access that server

        Args:
            mcp_runtime: MCP runtime instance to check
            server_id: Optional server ID to check for permission

        Raises:
            SkillMCPError: If runtime is unavailable or permission is denied

        Example:
            ```python
            # Check that MCP runtime is available
            SkillBase.requires_mcp(mcp_runtime)

            # Check that runtime has permission for specific server
            SkillBase.requires_mcp(mcp_runtime, "pg-readonly")
            ```
        """
        if mcp_runtime is None:
            error_msg = (
                "MCP runtime is required but not provided. "
                "This skill requires MCP integration to function."
            )
            logger.error(error_msg)
            raise SkillMCPError(error_msg)

        if server_id is not None:
            if not mcp_runtime.check_permission(server_id):
                error_msg = (
                    f"MCP runtime does not have permission to access server '{server_id}'. "
                    f"Required permission: mcp:{server_id}. "
                    f"Granted permissions: {mcp_runtime.get_granted_permissions()}"
                )
                logger.error(error_msg)
                raise SkillMCPError(error_msg)


__all__ = [
    # Protocols
    "Skill",
    "MCPSkill",
    # Helper class
    "SkillBase",
    # Exceptions
    "SkillValidationError",
    "SkillMCPError",
]
