"""Tests for MCP decorators."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from magsag.core.permissions import ToolPermission
from magsag.mcp.client import MCPClientError
from magsag.mcp.decorators import (
    _CLIENT_CACHE,
    _CLIENT_RETRY_OVERRIDES,
    _get_mcp_client,
    mcp_tool,
)


@pytest.mark.asyncio
async def test_mcp_tool_invokes_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure mcp_tool decorator delegates to AsyncMCPClient."""

    permission_mock = MagicMock()
    permission_mock.evaluate.return_value = ToolPermission.ALWAYS
    monkeypatch.setattr(
        "magsag.mcp.decorators._get_permission_evaluator", lambda: permission_mock
    )
    monkeypatch.setattr(
        "magsag.mcp.decorators._ensure_approval_gate",
        AsyncMock(return_value=None),
    )

    client_mock = SimpleNamespace(
        config={"limits": {"timeout_s": 15}},
        invoke=AsyncMock(return_value={"ok": True}),
    )
    monkeypatch.setattr(
        "magsag.mcp.decorators._get_mcp_client",
        AsyncMock(return_value=client_mock),
    )

    monkeypatch.setenv("DUMMY_TOKEN", "secret-token")

    @mcp_tool(server="git", tool="status", auth={"token": "env://DUMMY_TOKEN"})
    async def git_status() -> dict[str, Any]:
        return {}

    result = await git_status()

    client_mock.invoke.assert_awaited_once()
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_mcp_tool_handles_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure approval gate is invoked when required."""

    permission_mock = MagicMock()
    permission_mock.evaluate.return_value = ToolPermission.ALWAYS
    monkeypatch.setattr(
        "magsag.mcp.decorators._get_permission_evaluator", lambda: permission_mock
    )

    ticket = SimpleNamespace(ticket_id="ticket-1")
    gate_mock = SimpleNamespace(
        create_ticket=AsyncMock(return_value=ticket),
        wait_for_decision=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "magsag.mcp.decorators._ensure_approval_gate",
        AsyncMock(return_value=gate_mock),
    )

    client_mock = SimpleNamespace(
        config={"limits": {"timeout_s": 60}},
        invoke=AsyncMock(return_value={"result": "ok"}),
    )
    monkeypatch.setattr(
        "magsag.mcp.decorators._get_mcp_client",
        AsyncMock(return_value=client_mock),
    )

    monkeypatch.setenv("API_TOKEN", "token-value")

    @mcp_tool(
        server="git",
        tool="status",
        auth={"token": "env://API_TOKEN"},
        require_approval=True,
    )
    async def git_status(
        *,
        agent_slug: str,
        run_id: str,
        step_id: str,
        approval_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {}

    await git_status(agent_slug="agent-1", run_id="run-123", step_id="step-A", approval_metadata={"scope": "test"})

    create_call = gate_mock.create_ticket.await_args.kwargs
    assert create_call["run_id"] == "run-123"
    assert create_call["agent_slug"] == "agent-1"
    assert create_call["tool_name"] == "git.status"
    assert create_call["step_id"] == "step-A"
    assert create_call["metadata"]["scope"] == "test"

    permission_args = permission_mock.evaluate.call_args.args[1]
    masked_auth = permission_args["args"]["auth"]["token"]
    assert masked_auth == "***redacted***"

    invoke_args = client_mock.invoke.await_args.kwargs
    assert invoke_args["args"]["auth"]["token"] == "token-value"


@pytest.mark.asyncio
async def test_mcp_tool_denied_by_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    permission_mock = MagicMock()
    permission_mock.evaluate.return_value = ToolPermission.NEVER
    monkeypatch.setattr(
        "magsag.mcp.decorators._get_permission_evaluator", lambda: permission_mock
    )
    monkeypatch.setattr(
        "magsag.mcp.decorators._ensure_approval_gate",
        AsyncMock(return_value=None),
    )
    client_mock = SimpleNamespace(
        config={"limits": {"timeout_s": 30}},
        invoke=AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        "magsag.mcp.decorators._get_mcp_client",
        AsyncMock(return_value=client_mock),
    )

    @mcp_tool(server="git", tool="status")
    async def git_status() -> dict[str, Any]:
        return {}

    with pytest.raises(PermissionError):
        await git_status()

    client_mock.invoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_mcp_client_rejects_non_mcp_servers() -> None:
    """Ensure helper surfaces a clear error for non-MCP server types."""
    with pytest.raises(MCPClientError) as excinfo:
        await _get_mcp_client("pg-readonly", retry_attempts=None)

    assert "pg-readonly" in str(excinfo.value)


@pytest.mark.asyncio
async def test_get_mcp_client_respects_retry_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """First call with low retries should not affect later higher overrides."""

    from magsag.mcp.client import AsyncMCPClient

    original_cache = dict(_CLIENT_CACHE)
    original_overrides = dict(_CLIENT_RETRY_OVERRIDES)
    _CLIENT_CACHE.clear()
    _CLIENT_RETRY_OVERRIDES.clear()

    async def fake_initialize(self: AsyncMCPClient) -> None:
        self._initialized = True

    async def fake_close(self: AsyncMCPClient) -> None:
        self._initialized = False

    monkeypatch.setattr("magsag.mcp.client.AsyncMCPClient.initialize", fake_initialize)
    monkeypatch.setattr("magsag.mcp.client.AsyncMCPClient.close", fake_close)

    try:
        client_low = await _get_mcp_client("filesystem", 1)
        client_high = await _get_mcp_client("filesystem", 5)

        assert client_low is not client_high
        assert _CLIENT_RETRY_OVERRIDES["filesystem"] == 5
    finally:
        _CLIENT_CACHE.clear()
        _CLIENT_CACHE.update(original_cache)
        _CLIENT_RETRY_OVERRIDES.clear()
        _CLIENT_RETRY_OVERRIDES.update(original_overrides)


@pytest.mark.asyncio
async def test_mcp_tool_requires_gate_but_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    permission_mock = MagicMock()
    permission_mock.evaluate.return_value = ToolPermission.REQUIRE_APPROVAL
    monkeypatch.setattr(
        "magsag.mcp.decorators._get_permission_evaluator", lambda: permission_mock
    )
    monkeypatch.setattr(
        "magsag.mcp.decorators._ensure_approval_gate",
        AsyncMock(return_value=None),
    )
    client_mock = SimpleNamespace(
        config={"limits": {"timeout_s": 30}},
        invoke=AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        "magsag.mcp.decorators._get_mcp_client",
        AsyncMock(return_value=client_mock),
    )

    @mcp_tool(server="git", tool="status")
    async def git_status() -> dict[str, Any]:
        return {}

    with pytest.raises(PermissionError):
        await git_status()

    client_mock.invoke.assert_not_awaited()
