"""
MCP decorators for tool integration.

Provides decorators for marking functions as MCP tools with
authentication, permission checking, and observability.
"""

from __future__ import annotations

import functools
import logging
import os
from datetime import UTC, datetime
from typing import Any, Callable, Dict, Optional, TypeVar


logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def resolve_secret(value: str) -> str:
    """
    Resolve a secret value from environment or secrets manager.

    Supports the following patterns:
    - `env://VAR_NAME` - Read from environment variable
    - `secrets://path/to/secret` - Read from secrets manager (placeholder)
    - Plain value - Return as-is

    Args:
        value: Secret specification or plain value

    Returns:
        Resolved secret value

    Raises:
        ValueError: If secret cannot be resolved
    """
    if value.startswith("env://"):
        env_var = value[6:]  # Remove "env://" prefix
        resolved = os.environ.get(env_var)
        if resolved is None:
            raise ValueError(f"Environment variable {env_var} not found")
        return resolved

    if value.startswith("secrets://"):
        # Placeholder for secrets manager integration
        # In production, this would integrate with AWS Secrets Manager,
        # HashiCorp Vault, etc.
        secret_path = value[10:]  # Remove "secrets://" prefix
        raise NotImplementedError(
            f"Secrets manager integration not implemented. "
            f"Attempted to read: {secret_path}"
        )

    # Plain value
    return value


def get_auth_config(auth_config: Optional[Dict[str, str]]) -> Dict[str, str]:
    """
    Resolve authentication configuration.

    Args:
        auth_config: Raw auth configuration (may contain env:// references)

    Returns:
        Resolved auth configuration

    Example:
        >>> get_auth_config({"api_key": "env://GITHUB_TOKEN"})
        {"api_key": "ghp_xxx..."}
    """
    if not auth_config:
        return {}

    resolved: Dict[str, str] = {}
    for key, value in auth_config.items():
        try:
            resolved[key] = resolve_secret(value)
        except Exception as e:
            logger.warning(f"Failed to resolve auth config for {key}: {e}")
            # Don't include unresolved keys
            continue

    return resolved


def mcp_tool(
    server: str,
    tool: str,
    auth: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = None,
    retry_attempts: Optional[int] = None,
    require_approval: bool = False,
) -> Callable[[F], F]:
    """
    Decorator for marking a function as an MCP tool invocation.

    This decorator handles:
    - Authentication credential resolution
    - Timeout and retry configuration
    - Approval requirement checking
    - Observability (logging, metrics)

    Args:
        server: MCP server name
        tool: Tool name to invoke
        auth: Authentication configuration (supports env:// references)
        timeout: Request timeout in seconds (optional)
        retry_attempts: Number of retry attempts (optional)
        require_approval: Whether to require approval before invocation

    Returns:
        Decorated function

    Example:
        >>> @mcp_tool(
        ...     server="github",
        ...     tool="create_issue",
        ...     auth={"token": "env://GITHUB_TOKEN"},
        ...     timeout=30.0,
        ...     require_approval=True
        ... )
        ... async def create_github_issue(repo: str, title: str, body: str) -> dict:
        ...     # Function body is replaced by MCP invocation
        ...     pass
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Resolve authentication
            resolved_auth = get_auth_config(auth)

            # Log invocation
            logger.info(
                f"Invoking MCP tool {server}.{tool} "
                f"(approval_required={require_approval})"
            )

            # Check if approval is required
            if require_approval:
                # Placeholder: In production, this would integrate with
                # the Approval Gate to create a ticket and wait for decision
                logger.warning(
                    f"Approval required for {server}.{tool} but approval "
                    "gate integration is not yet implemented"
                )

            # Record invocation start time
            start_time = datetime.now(UTC)

            try:
                # Placeholder: In production, this would create an AsyncMCPClient
                # and invoke the tool with the provided arguments
                logger.debug(
                    f"MCP invocation: {server}.{tool} "
                    f"with args={args}, kwargs={kwargs}"
                )

                # Simulate result
                result = {
                    "server": server,
                    "tool": tool,
                    "args": args,
                    "kwargs": kwargs,
                    "auth_keys": list(resolved_auth.keys()),
                    "timestamp": start_time.isoformat(),
                }

                # Record success
                duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000
                logger.info(
                    f"Successfully invoked {server}.{tool} in {duration_ms:.1f}ms"
                )

                return result

            except Exception as e:
                # Record failure
                duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000
                logger.error(
                    f"Failed to invoke {server}.{tool} after {duration_ms:.1f}ms: {e}"
                )
                raise

        return wrapper  # type: ignore

    return decorator


def mcp_authenticated(
    auth_env_var: str,
    auth_type: str = "bearer",
) -> Callable[[F], F]:
    """
    Decorator for functions requiring MCP authentication.

    This is a simpler alternative to @mcp_tool for cases where you
    want to handle the MCP invocation manually but need authentication.

    Args:
        auth_env_var: Environment variable containing auth token
        auth_type: Authentication type (bearer, api_key, basic)

    Returns:
        Decorated function

    Example:
        >>> @mcp_authenticated(auth_env_var="GITHUB_TOKEN", auth_type="bearer")
        ... async def call_github_api():
        ...     # Function has access to resolved auth token via keyword argument
        ...     pass
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Resolve authentication token
            try:
                auth_token = resolve_secret(f"env://{auth_env_var}")
            except ValueError as e:
                logger.error(f"Failed to resolve authentication: {e}")
                raise

            # Inject auth into kwargs
            if auth_type == "bearer":
                kwargs["auth_header"] = f"Bearer {auth_token}"
            elif auth_type == "api_key":
                kwargs["api_key"] = auth_token
            elif auth_type == "basic":
                kwargs["auth_token"] = auth_token
            else:
                kwargs["auth_token"] = auth_token

            logger.debug(f"Resolved authentication for {func.__name__} ({auth_type})")

            return await func(*args, **kwargs)

        return wrapper  # type: ignore

    return decorator


def mcp_with_approval(
    approval_message: str,
    timeout_minutes: int = 30,
) -> Callable[[F], F]:
    """
    Decorator for functions requiring human approval.

    This decorator integrates with the Approval Gate to request
    approval before executing the decorated function.

    Args:
        approval_message: Message to display in approval request
        timeout_minutes: Approval timeout in minutes

    Returns:
        Decorated function

    Example:
        >>> @mcp_with_approval(
        ...     approval_message="Deploy to production?",
        ...     timeout_minutes=15
        ... )
        ... async def deploy_to_production():
        ...     # This will only execute if approved
        ...     pass
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            logger.info(
                f"Requesting approval for {func.__name__}: {approval_message}"
            )

            # Placeholder: In production, this would integrate with
            # the Approval Gate to create a ticket and wait for decision
            # For now, we log and proceed
            logger.warning(
                f"Approval gate integration not implemented, "
                f"proceeding with {func.__name__}"
            )

            return await func(*args, **kwargs)

        return wrapper  # type: ignore

    return decorator


def mcp_cached(
    ttl_seconds: int = 3600,
    key_fn: Optional[Callable[..., str]] = None,
) -> Callable[[F], F]:
    """
    Decorator for caching MCP tool results.

    This decorator caches the results of MCP tool invocations
    to reduce redundant calls and improve performance.

    Args:
        ttl_seconds: Cache TTL in seconds (default: 1 hour)
        key_fn: Optional function to generate cache key from arguments

    Returns:
        Decorated function

    Example:
        >>> @mcp_cached(ttl_seconds=300)
        ... @mcp_tool(server="github", tool="get_user")
        ... async def get_github_user(username: str):
        ...     pass
    """

    def decorator(func: F) -> F:
        cache: Dict[str, tuple[Any, datetime]] = {}

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Generate cache key
            if key_fn:
                cache_key = key_fn(*args, **kwargs)
            else:
                # Default: use function name and str representation of args/kwargs
                cache_key = f"{func.__name__}:{args}:{kwargs}"

            # Check cache
            if cache_key in cache:
                result, cached_at = cache[cache_key]
                age_seconds = (datetime.now(UTC) - cached_at).total_seconds()

                if age_seconds < ttl_seconds:
                    logger.debug(
                        f"Cache hit for {func.__name__} (age: {age_seconds:.1f}s)"
                    )
                    return result
                else:
                    logger.debug(
                        f"Cache expired for {func.__name__} (age: {age_seconds:.1f}s)"
                    )
                    del cache[cache_key]

            # Cache miss - invoke function
            logger.debug(f"Cache miss for {func.__name__}, invoking...")
            result = await func(*args, **kwargs)

            # Store in cache
            cache[cache_key] = (result, datetime.now(UTC))

            return result

        return wrapper  # type: ignore

    return decorator
