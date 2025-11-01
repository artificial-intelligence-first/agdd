"""
MCP decorators for tool integration.

Provides decorators for marking functions as MCP tools with
authentication, permission checking, and observability.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional, TypeVar

import yaml

from magsag.api.config import get_settings
from magsag.core.permissions import ToolPermission, mask_tool_args
from magsag.governance.approval_gate import ApprovalGate
from magsag.governance.permission_evaluator import PermissionEvaluator
from magsag.mcp.client import (
    AsyncMCPClient,
    MCPClientError,
    MCPTransportError,
    RetryConfig,
    TransportType,
)
from magsag.mcp.config import MCPServerConfig
from magsag.storage import get_storage_backend


logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

_CLIENT_CACHE: dict[str, "AsyncMCPClient"] = {}
_CLIENT_RETRY_OVERRIDES: dict[str, Optional[int]] = {}
_CLIENT_LOCK = asyncio.Lock()
_SERVER_CONFIG_CACHE: dict[str, "MCPServerConfig"] = {}
_PERMISSION_EVALUATOR: Optional["PermissionEvaluator"] = None
_APPROVAL_GATE: Optional["ApprovalGate"] = None
_APPROVAL_GATE_LOCK = asyncio.Lock()


def _servers_dir() -> Path:
    return Path.cwd() / ".mcp" / "servers"


def _load_server_config(server_id: str) -> MCPServerConfig:
    if server_id in _SERVER_CONFIG_CACHE:
        return _SERVER_CONFIG_CACHE[server_id]

    config_path = _servers_dir() / f"{server_id}.yaml"
    if not config_path.exists():
        raise MCPClientError(f"MCP server config not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as handle:
        raw_data = yaml.safe_load(handle) or {}

    config = MCPServerConfig(**raw_data)
    config.validate_type_fields()

    _SERVER_CONFIG_CACHE[server_id] = config
    return config


def _get_permission_evaluator() -> PermissionEvaluator:
    global _PERMISSION_EVALUATOR
    if _PERMISSION_EVALUATOR is None:
        policy_path = Path("catalog/policies/mcp_permissions.yaml")
        _PERMISSION_EVALUATOR = PermissionEvaluator(policy_path=policy_path)
    return _PERMISSION_EVALUATOR


async def _ensure_approval_gate() -> Optional[ApprovalGate]:
    settings = get_settings()
    if not settings.APPROVALS_ENABLED:
        return None

    global _APPROVAL_GATE
    async with _APPROVAL_GATE_LOCK:
        if _APPROVAL_GATE is not None:
            return _APPROVAL_GATE

        evaluator = _get_permission_evaluator()
        storage = await get_storage_backend(settings)
        _APPROVAL_GATE = ApprovalGate(
            permission_evaluator=evaluator,
            ticket_store=storage,
            default_timeout_minutes=settings.APPROVAL_TTL_MIN,
        )
        return _APPROVAL_GATE


async def _get_mcp_client(server_id: str, retry_attempts: Optional[int]) -> AsyncMCPClient:
    async with _CLIENT_LOCK:
        if server_id in _CLIENT_CACHE:
            cached_retry = _CLIENT_RETRY_OVERRIDES.get(server_id)
            normalized_retry = retry_attempts or None
            if cached_retry == normalized_retry:
                return _CLIENT_CACHE[server_id]

            # Retry configuration differs; reinitialize the client
            await _CLIENT_CACHE[server_id].close()
            del _CLIENT_CACHE[server_id]
            _CLIENT_RETRY_OVERRIDES.pop(server_id, None)

        config = _load_server_config(server_id)

        if config.type != "mcp":
            raise MCPClientError(
                f"Server '{server_id}' is type '{config.type}', which is not compatible with the MCP client "
                "decorators. Use the dedicated runtime helpers for non-MCP backends."
            )

        transport_name = config.transport or "stdio"
        retry_config = RetryConfig(max_attempts=retry_attempts) if retry_attempts else None

        if transport_name == "stdio":
            client_config = {
                "command": config.command,
                "args": config.args,
                "limits": config.limits.model_dump(),
            }
            client = AsyncMCPClient(
                server_name=server_id,
                transport=TransportType.STDIO,
                config=client_config,
                retry_config=retry_config,
            )
        elif transport_name == "http":
            client_config = {
                "url": config.url,
                "headers": config.headers,
                "limits": config.limits.model_dump(),
            }
            client = AsyncMCPClient(
                server_name=server_id,
                transport=TransportType.HTTP,
                config=client_config,
                retry_config=retry_config,
            )
        elif transport_name == "websocket":
            client_config = {
                "url": config.url,
                "headers": config.headers,
                "limits": config.limits.model_dump(),
            }
            client = AsyncMCPClient(
                server_name=server_id,
                transport=TransportType.WEBSOCKET,
                config=client_config,
                retry_config=retry_config,
            )
        else:
            raise MCPTransportError(f"Unsupported transport '{transport_name}' for server '{server_id}'")
        _CLIENT_CACHE[server_id] = client
        _CLIENT_RETRY_OVERRIDES[server_id] = retry_attempts or None

    await client.initialize()
    return client


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
        signature = inspect.signature(func)

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            resolved_auth = get_auth_config(auth)
            bound = signature.bind_partial(*args, **kwargs)
            bound.apply_defaults()

            call_args = dict(bound.arguments)
            call_args.pop("self", None)
            call_args.pop("cls", None)
            context_metadata = call_args.pop("approval_metadata", None)
            run_id = call_args.pop("run_id", None) or f"mcp-{uuid.uuid4().hex[:8]}"
            agent_slug = call_args.pop("agent_slug", None) or "mcp-client"
            step_id = call_args.get("step_id", tool)

            rpc_params = call_args.copy()
            for meta_key in ("step_id",):
                rpc_params.pop(meta_key, None)

            if resolved_auth:
                rpc_params.setdefault("auth", resolved_auth)

            evaluator = _get_permission_evaluator()
            permission_context = {
                "server": server,
                "tool": tool,
                "agent_slug": agent_slug,
                "args": mask_tool_args(rpc_params),
            }
            permission = evaluator.evaluate(f"{server}.{tool}", permission_context)

            if permission == ToolPermission.NEVER:
                raise PermissionError(f"MCP tool {server}.{tool} is not allowed by policy")

            approval_needed = require_approval or permission == ToolPermission.REQUIRE_APPROVAL

            if approval_needed:
                approval_gate = await _ensure_approval_gate()
                if approval_gate is None:
                    raise PermissionError(
                        f"Approval required for {server}.{tool} but approval gate is disabled"
                    )

                metadata: Dict[str, Any] = {"server": server, "tool": tool}
                if isinstance(context_metadata, dict):
                    metadata.update(context_metadata)

                ticket = await approval_gate.create_ticket(
                    run_id=run_id,
                    agent_slug=agent_slug,
                    tool_name=f"{server}.{tool}",
                    tool_args=rpc_params,
                    step_id=str(step_id),
                    metadata=metadata,
                )
                await approval_gate.wait_for_decision(ticket)

            client = await _get_mcp_client(server, retry_attempts)
            effective_timeout = timeout
            if effective_timeout is None:
                limits = client.config.get("limits") or {}
                effective_timeout = limits.get("timeout_s")

            logger.info("Invoking MCP tool %s.%s (run_id=%s)", server, tool, run_id)

            start_time = datetime.now(UTC)
            try:
                result = await client.invoke(
                    tool=tool,
                    args=rpc_params,
                    timeout=effective_timeout,
                )
                duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000
                logger.info(
                    "MCP tool %s.%s completed in %.1f ms",
                    server,
                    tool,
                    duration_ms,
                )
                return result
            except (MCPClientError, MCPTransportError) as exc:
                duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000
                logger.error(
                    "MCP invocation %s.%s failed after %.1f ms: %s",
                    server,
                    tool,
                    duration_ms,
                    exc,
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

            approval_gate = await _ensure_approval_gate()
            if approval_gate is not None:
                run_id = kwargs.get("run_id") or f"mcp-{uuid.uuid4().hex[:8]}"
                agent_slug = kwargs.get("agent_slug", "mcp-client")
                ticket = await approval_gate.create_ticket(
                    run_id=run_id,
                    agent_slug=agent_slug,
                    tool_name=f"decorator.{func.__name__}",
                    tool_args={"args": args, "kwargs": kwargs},
                    metadata={"message": approval_message},
                    timeout_minutes=timeout_minutes,
                )
                await approval_gate.wait_for_decision(ticket)
            else:
                logger.warning(
                    "Approval gate disabled; proceeding with %s without approval",
                    func.__name__,
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
