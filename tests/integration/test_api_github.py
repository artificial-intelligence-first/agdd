"""Integration tests for GitHub webhook API."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from agdd.api.config import Settings, get_settings
from agdd.api.server import app


pytestmark = pytest.mark.slow


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    """Create test settings with GitHub configuration."""
    settings = Settings()
    settings.GITHUB_WEBHOOK_SECRET = "test-secret"
    settings.GITHUB_TOKEN = "test-token"
    settings.RUNS_BASE_DIR = str(tmp_path / "runs")
    return settings


@pytest.fixture
def client_with_github(test_settings: Settings) -> Iterator[TestClient]:
    """Create test client with GitHub settings."""

    def override_settings() -> Settings:
        return test_settings

    app.dependency_overrides[get_settings] = override_settings
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def compute_signature(secret: str, payload: bytes) -> str:
    """Compute GitHub webhook signature."""
    mac = hmac.new(secret.encode(), payload, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


def test_webhook_health(client_with_github: TestClient) -> None:
    """Test GitHub integration health check."""
    response = client_with_github.get("/api/v1/github/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["integration"] == "github"


def test_webhook_signature_verification_fails(client_with_github: TestClient) -> None:
    """Test that invalid signature is rejected."""
    payload = {"action": "created", "comment": {"body": "test"}}
    payload_bytes = json.dumps(payload).encode()

    response = client_with_github.post(
        "/api/v1/github/webhook",
        content=payload_bytes,
        headers={
            "X-GitHub-Event": "issue_comment",
            "X-Hub-Signature-256": "sha256=invalid",
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 401
    data = response.json()
    assert data["code"] == "invalid_signature"


def test_webhook_signature_verification_succeeds(client_with_github: TestClient) -> None:
    """Test that valid signature is accepted."""
    payload = {
        "action": "created",
        "repository": {"full_name": "owner/repo"},
        "issue": {"number": 1},
        "comment": {"body": "No commands here"},
    }
    payload_bytes = json.dumps(payload).encode()
    signature = compute_signature("test-secret", payload_bytes)

    response = client_with_github.post(
        "/api/v1/github/webhook",
        content=payload_bytes,
        headers={
            "X-GitHub-Event": "issue_comment",
            "X-Hub-Signature-256": signature,
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@patch("agdd.integrations.github.webhook.post_comment", new_callable=AsyncMock)
@patch("agdd.integrations.github.webhook.invoke_mag")
def test_webhook_issue_comment_with_command(
    mock_invoke: Any,
    mock_post: AsyncMock,
    client_with_github: TestClient,
    tmp_path: Path,
) -> None:
    """Test processing issue comment with agent command."""
    # Setup mock
    mock_invoke.return_value = {"result": "success", "data": 42}

    # Create runs directory
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()

    payload = {
        "action": "created",
        "repository": {"full_name": "owner/repo"},
        "issue": {"number": 123},
        "comment": {"body": '@test-agent {"input": "data"}'},
    }
    payload_bytes = json.dumps(payload).encode()
    signature = compute_signature("test-secret", payload_bytes)

    response = client_with_github.post(
        "/api/v1/github/webhook",
        content=payload_bytes,
        headers={
            "X-GitHub-Event": "issue_comment",
            "X-Hub-Signature-256": signature,
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    # Verify invoke_mag was called
    assert mock_invoke.called
    call_args = mock_invoke.call_args
    assert call_args[0][0] == "test-agent"
    assert call_args[0][1] == {"input": "data"}

    # Verify comment was posted
    assert mock_post.called
    post_args = mock_post.call_args[0]
    assert post_args[0] == "owner/repo"
    assert post_args[1] == 123
    assert "✅" in post_args[2]  # Success message
    assert "test-agent" in post_args[2]


@patch("agdd.integrations.github.webhook.post_comment", new_callable=AsyncMock)
@patch("agdd.integrations.github.webhook.invoke_mag")
def test_webhook_agent_execution_failure(
    mock_invoke: Any,
    mock_post: AsyncMock,
    client_with_github: TestClient,
    tmp_path: Path,
) -> None:
    """Test handling agent execution failure."""
    # Setup mock to raise exception
    mock_invoke.side_effect = RuntimeError("Agent failed")

    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()

    payload = {
        "action": "created",
        "repository": {"full_name": "owner/repo"},
        "issue": {"number": 456},
        "comment": {"body": '@failing-agent {"input": "bad"}'},
    }
    payload_bytes = json.dumps(payload).encode()
    signature = compute_signature("test-secret", payload_bytes)

    response = client_with_github.post(
        "/api/v1/github/webhook",
        content=payload_bytes,
        headers={
            "X-GitHub-Event": "issue_comment",
            "X-Hub-Signature-256": signature,
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 200

    # Verify error comment was posted
    assert mock_post.called
    post_args = mock_post.call_args[0]
    assert "❌" in post_args[2]  # Error message
    assert "failing-agent" in post_args[2]
    assert "Agent failed" in post_args[2]


def test_webhook_unsupported_event(client_with_github: TestClient) -> None:
    """Test that unsupported events are ignored gracefully."""
    payload = {"action": "opened"}
    payload_bytes = json.dumps(payload).encode()
    signature = compute_signature("test-secret", payload_bytes)

    response = client_with_github.post(
        "/api/v1/github/webhook",
        content=payload_bytes,
        headers={
            "X-GitHub-Event": "unsupported_event",
            "X-Hub-Signature-256": signature,
            "Content-Type": "application/json",
        },
    )

    # Should succeed but do nothing
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_webhook_no_commands_in_comment(client_with_github: TestClient) -> None:
    """Test that comments without commands are ignored."""
    payload = {
        "action": "created",
        "repository": {"full_name": "owner/repo"},
        "issue": {"number": 789},
        "comment": {"body": "This is just a regular comment"},
    }
    payload_bytes = json.dumps(payload).encode()
    signature = compute_signature("test-secret", payload_bytes)

    response = client_with_github.post(
        "/api/v1/github/webhook",
        content=payload_bytes,
        headers={
            "X-GitHub-Event": "issue_comment",
            "X-Hub-Signature-256": signature,
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
