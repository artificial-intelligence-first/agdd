"""Pytest configuration helpers."""

from __future__ import annotations

import importlib
import os
from typing import Iterator

import pytest


@pytest.fixture(scope="session", autouse=True)
def disable_mcp_for_tests() -> Iterator[None]:
    """Disable MCP integrations during tests unless explicitly re-enabled.

    Heavyweight MCP servers (e.g. npx-based helpers) slow down or hang
    parallel test workers. Setting ``AGDD_ENABLE_MCP=0`` keeps the default
    agent runner lightweight while individual tests can override it.
    """

    previous = os.getenv("AGDD_ENABLE_MCP")
    os.environ["AGDD_ENABLE_MCP"] = "0"

    # Ensure agdd.mcp exports server provider helpers even with MCP disabled.
    try:
        mcp_module = importlib.import_module("agdd.mcp")
        if not getattr(mcp_module, "HAS_SERVER_PROVIDER", False):
            server_provider = importlib.import_module("agdd.mcp.server_provider")
            setattr(mcp_module, "AGDDMCPServer", getattr(server_provider, "AGDDMCPServer", None))
            setattr(mcp_module, "create_server", getattr(server_provider, "create_server", None))
            setattr(
                mcp_module,
                "HAS_SERVER_PROVIDER",
                bool(getattr(server_provider, "HAS_MCP_SDK", False)),
            )
    except ImportError:
        # If MCP modules are unavailable the slow MCP tests will skip as expected.
        pass
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("AGDD_ENABLE_MCP", None)
        else:
            os.environ["AGDD_ENABLE_MCP"] = previous
