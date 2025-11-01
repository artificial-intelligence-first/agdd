"""Integration tests for API error responses."""

from __future__ import annotations

import json

import anyio
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from magsag.api.server import app, http_exception_handler

import pytest

pytestmark = pytest.mark.slow

client = TestClient(app)


def test_unknown_route_returns_api_error() -> None:
    """Requests to unknown routes should return ApiError schema."""
    response = client.get("/api/v1/__missing__")
    assert response.status_code == 404
    data = response.json()
    assert data["code"] == "not_found"
    assert "message" in data


def test_method_not_allowed_returns_api_error() -> None:
    """Requests with wrong HTTP method should return ApiError schema."""
    response = client.post("/api/v1/agents")
    assert response.status_code == 405
    data = response.json()
    assert data["code"] == "method_not_allowed"
    assert "message" in data


def test_http_exception_handler_maps_forbidden() -> None:
    """HTTPException 403 should map to forbidden code."""

    async def runner() -> None:
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"",
            "client": ("testclient", 0),
            "server": ("testserver", 80),
        }

        async def receive() -> dict[str, object]:
            return {"type": "http.request", "body": b"", "more_body": False}

        request = Request(scope, receive)
        response = await http_exception_handler(
            request, HTTPException(status_code=403, detail="Forbidden")
        )
        assert response.status_code == 403
        body_bytes = bytes(response.body)
        data = json.loads(body_bytes.decode("utf-8"))
        assert data["code"] == "forbidden"
        assert data["message"] == "Forbidden"

    anyio.run(runner, backend="asyncio")
