"""Unit tests for Approval Gate."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agdd.core.permissions import ToolPermission
from agdd.governance.approval_gate import (
    ApprovalDeniedError,
    ApprovalGate,
    ApprovalTimeoutError,
)
from agdd.governance.permission_evaluator import PermissionEvaluator


class TestPermissionEvaluator:
    """Test permission evaluator."""

    @pytest.fixture
    def policy_file(self) -> Path:
        """Create a temporary policy file."""
        policy_content = """
default_permission: REQUIRE_APPROVAL

tools:
  "filesystem.read_file":
    permission: ALWAYS
    description: "Read file is safe"

  "filesystem.write_file":
    permission: REQUIRE_APPROVAL
    description: "Write file requires approval"

  "database.delete":
    permission: NEVER
    description: "Delete is not allowed"

categories:
  read_only:
    permission: ALWAYS
    tools:
      - "*.get_*"
      - "*.list_*"

dangerous_patterns:
  - pattern: "*.drop_*"
    permission: NEVER

environments:
  development:
    default_permission: ALWAYS
    overrides:
      "database.delete": REQUIRE_APPROVAL
"""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml") as f:
            f.write(policy_content)
            return Path(f.name)

    def test_evaluate_always_permission(self, policy_file: Path) -> None:
        """Test evaluating ALWAYS permission."""
        evaluator = PermissionEvaluator(policy_path=policy_file)

        permission = evaluator.evaluate("filesystem.read_file", {})
        assert permission == ToolPermission.ALWAYS

    def test_evaluate_require_approval_permission(self, policy_file: Path) -> None:
        """Test evaluating REQUIRE_APPROVAL permission."""
        evaluator = PermissionEvaluator(policy_path=policy_file)

        permission = evaluator.evaluate("filesystem.write_file", {})
        assert permission == ToolPermission.REQUIRE_APPROVAL

    def test_evaluate_never_permission(self, policy_file: Path) -> None:
        """Test evaluating NEVER permission."""
        evaluator = PermissionEvaluator(policy_path=policy_file)

        permission = evaluator.evaluate("database.delete", {})
        assert permission == ToolPermission.NEVER

    def test_evaluate_category_permission(self, policy_file: Path) -> None:
        """Test evaluating category-based permission."""
        evaluator = PermissionEvaluator(policy_path=policy_file)

        permission = evaluator.evaluate("api.get_user", {})
        assert permission == ToolPermission.ALWAYS

        permission = evaluator.evaluate("api.list_repos", {})
        assert permission == ToolPermission.ALWAYS

    def test_evaluate_dangerous_pattern(self, policy_file: Path) -> None:
        """Test evaluating dangerous patterns."""
        evaluator = PermissionEvaluator(policy_path=policy_file)

        permission = evaluator.evaluate("database.drop_table", {})
        assert permission == ToolPermission.NEVER

    def test_evaluate_environment_override(self, policy_file: Path) -> None:
        """Test environment-specific overrides."""
        evaluator = PermissionEvaluator(
            policy_path=policy_file,
            environment="development",
        )

        # In development, database.delete is REQUIRE_APPROVAL
        permission = evaluator.evaluate("database.delete", {})
        assert permission == ToolPermission.REQUIRE_APPROVAL

    def test_evaluate_default_permission(self, policy_file: Path) -> None:
        """Test falling back to default permission."""
        evaluator = PermissionEvaluator(policy_path=policy_file)

        # Unknown tool should use default
        permission = evaluator.evaluate("unknown.tool", {})
        assert permission == ToolPermission.REQUIRE_APPROVAL


class TestApprovalGate:
    """Test approval gate functionality."""

    @pytest.fixture
    def evaluator(self) -> PermissionEvaluator:
        """Create a permission evaluator."""
        policy_content = """
default_permission: REQUIRE_APPROVAL

tools:
  "safe.tool":
    permission: ALWAYS

  "requires_approval.tool":
    permission: REQUIRE_APPROVAL

  "dangerous.tool":
    permission: NEVER
"""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml") as f:
            f.write(policy_content)
            policy_file = Path(f.name)

        return PermissionEvaluator(policy_path=policy_file)

    @pytest.fixture
    def gate(self, evaluator: PermissionEvaluator) -> ApprovalGate:
        """Create an approval gate."""
        return ApprovalGate(
            permission_evaluator=evaluator,
            default_timeout_minutes=1,  # Short timeout for testing
        )

    def test_evaluate_always(self, gate: ApprovalGate) -> None:
        """Test evaluating ALWAYS permission."""
        permission = gate.evaluate("safe.tool", {})
        assert permission == ToolPermission.ALWAYS

    def test_evaluate_require_approval(self, gate: ApprovalGate) -> None:
        """Test evaluating REQUIRE_APPROVAL permission."""
        permission = gate.evaluate("requires_approval.tool", {})
        assert permission == ToolPermission.REQUIRE_APPROVAL

    def test_evaluate_never(self, gate: ApprovalGate) -> None:
        """Test evaluating NEVER permission."""
        permission = gate.evaluate("dangerous.tool", {})
        assert permission == ToolPermission.NEVER

    def test_create_ticket(self, gate: ApprovalGate) -> None:
        """Test creating an approval ticket."""
        ticket = gate.create_ticket(
            run_id="run-123",
            agent_slug="test-agent",
            tool_name="test.tool",
            tool_args={"arg": "value"},
        )

        assert ticket.ticket_id is not None
        assert ticket.run_id == "run-123"
        assert ticket.agent_slug == "test-agent"
        assert ticket.tool_name == "test.tool"
        assert ticket.tool_args == {"arg": "value"}
        assert ticket.status == "pending"
        assert isinstance(ticket.requested_at, datetime)
        assert isinstance(ticket.expires_at, datetime)

    def test_get_ticket(self, gate: ApprovalGate) -> None:
        """Test retrieving an approval ticket."""
        ticket = gate.create_ticket(
            run_id="run-123",
            agent_slug="test-agent",
            tool_name="test.tool",
            tool_args={},
        )

        retrieved = gate.get_ticket(ticket.ticket_id)
        assert retrieved is not None
        assert retrieved.ticket_id == ticket.ticket_id
        assert retrieved.status == "pending"

    def test_get_nonexistent_ticket(self, gate: ApprovalGate) -> None:
        """Test retrieving a non-existent ticket."""
        retrieved = gate.get_ticket("nonexistent-id")
        assert retrieved is None

    def test_approve_ticket(self, gate: ApprovalGate) -> None:
        """Test approving a ticket."""
        ticket = gate.create_ticket(
            run_id="run-123",
            agent_slug="test-agent",
            tool_name="test.tool",
            tool_args={},
        )

        approved = gate.approve_ticket(
            ticket_id=ticket.ticket_id,
            approved_by="admin@example.com",
        )

        assert approved.status == "approved"
        assert approved.resolved_by == "admin@example.com"
        assert approved.resolved_at is not None

    def test_deny_ticket(self, gate: ApprovalGate) -> None:
        """Test denying a ticket."""
        ticket = gate.create_ticket(
            run_id="run-123",
            agent_slug="test-agent",
            tool_name="test.tool",
            tool_args={},
        )

        denied = gate.deny_ticket(
            ticket_id=ticket.ticket_id,
            denied_by="admin@example.com",
            reason="Not allowed",
        )

        assert denied.status == "denied"
        assert denied.resolved_by == "admin@example.com"
        assert denied.resolved_at is not None
        assert denied.response == {"reason": "Not allowed"}

    def test_list_pending_tickets(self, gate: ApprovalGate) -> None:
        """Test listing pending tickets."""
        # Create tickets
        ticket1 = gate.create_ticket(
            run_id="run-123",
            agent_slug="agent-1",
            tool_name="tool1",
            tool_args={},
        )
        ticket2 = gate.create_ticket(
            run_id="run-123",
            agent_slug="agent-2",
            tool_name="tool2",
            tool_args={},
        )

        # Approve one
        gate.approve_ticket(ticket1.ticket_id, "admin")

        # List all pending
        pending = gate.list_pending_tickets()
        assert len(pending) == 1
        assert pending[0].ticket_id == ticket2.ticket_id

        # Filter by agent
        pending_agent2 = gate.list_pending_tickets(agent_slug="agent-2")
        assert len(pending_agent2) == 1
        assert pending_agent2[0].ticket_id == ticket2.ticket_id

    def test_expire_old_tickets(self, gate: ApprovalGate) -> None:
        """Test expiring old tickets."""
        # Create a ticket
        ticket = gate.create_ticket(
            run_id="run-123",
            agent_slug="test-agent",
            tool_name="test.tool",
            tool_args={},
            timeout_minutes=0,  # Expire immediately
        )

        # Force expiration by setting expires_at in the past
        ticket.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        gate._tickets[ticket.ticket_id] = ticket

        # Expire old tickets
        count = gate.expire_old_tickets()
        assert count == 1

        # Verify ticket is expired
        expired = gate.get_ticket(ticket.ticket_id)
        assert expired is not None
        assert expired.status == "expired"

    async def test_wait_for_decision_approved(self, gate: ApprovalGate) -> None:
        """Test waiting for approval decision."""
        import asyncio

        ticket = gate.create_ticket(
            run_id="run-123",
            agent_slug="test-agent",
            tool_name="test.tool",
            tool_args={},
        )

        # Approve ticket after a short delay
        async def approve_later() -> None:
            await asyncio.sleep(0.1)
            gate.approve_ticket(ticket.ticket_id, "admin")

        # Start approval task
        approve_task = asyncio.create_task(approve_later())

        # Wait for decision
        result = await gate.wait_for_decision(ticket, poll_interval_seconds=0.05)
        assert result.status == "approved"

        await approve_task

    async def test_wait_for_decision_denied(self, gate: ApprovalGate) -> None:
        """Test waiting for denial decision."""
        import asyncio

        ticket = gate.create_ticket(
            run_id="run-123",
            agent_slug="test-agent",
            tool_name="test.tool",
            tool_args={},
        )

        # Deny ticket after a short delay
        async def deny_later() -> None:
            await asyncio.sleep(0.1)
            gate.deny_ticket(ticket.ticket_id, "admin", "Test denial")

        # Start denial task
        deny_task = asyncio.create_task(deny_later())

        # Wait for decision (should raise)
        with pytest.raises(ApprovalDeniedError):
            await gate.wait_for_decision(ticket, poll_interval_seconds=0.05)

        await deny_task

    async def test_wait_for_decision_timeout(self, gate: ApprovalGate) -> None:
        """Test waiting for decision timeout."""
        ticket = gate.create_ticket(
            run_id="run-123",
            agent_slug="test-agent",
            tool_name="test.tool",
            tool_args={},
            timeout_minutes=0,  # Expire immediately
        )

        # Force immediate expiration
        ticket.expires_at = datetime.now(UTC) + timedelta(milliseconds=100)
        gate._tickets[ticket.ticket_id] = ticket

        # Wait for decision (should timeout)
        with pytest.raises(ApprovalTimeoutError):
            await gate.wait_for_decision(ticket, poll_interval_seconds=0.05)
