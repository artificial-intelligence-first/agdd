"""
Integration tests for Handoff-as-a-Tool.

Tests the complete handoff lifecycle including:
- Handoff request creation
- Platform-specific adapters
- Policy enforcement
- Multi-platform support
"""

import pytest

from agdd.core.permissions import ToolPermission
from agdd.governance.permission_evaluator import PermissionEvaluator
from agdd.routing.handoff_tool import (
    AGDDHandoffAdapter,
    ADKHandoffAdapter,
    AnthropicHandoffAdapter,
    HandoffRequest,
    HandoffTool,
    OpenAIHandoffAdapter,
)


@pytest.fixture
def handoff_tool():
    """Create handoff tool for testing."""
    return HandoffTool(
        permission_evaluator=None,  # No permission checks for basic tests
        approval_gate=None,
    )


@pytest.fixture
def handoff_tool_with_permissions():
    """Create handoff tool with permission evaluator."""
    evaluator = PermissionEvaluator()
    return HandoffTool(
        permission_evaluator=evaluator,
        approval_gate=None,
    )


class TestHandoffAdapters:
    """Tests for platform-specific handoff adapters."""

    def test_agdd_adapter_supports_platform(self):
        """Test AGDD adapter platform detection."""
        adapter = AGDDHandoffAdapter()

        assert adapter.supports_platform("agdd")
        assert adapter.supports_platform("native")
        assert adapter.supports_platform("AGDD")  # Case insensitive
        assert not adapter.supports_platform("openai")

    def test_adk_adapter_supports_platform(self):
        """Test ADK adapter platform detection."""
        adapter = ADKHandoffAdapter()

        assert adapter.supports_platform("adk")
        assert adapter.supports_platform("anthropic-adk")
        assert not adapter.supports_platform("agdd")

    def test_openai_adapter_supports_platform(self):
        """Test OpenAI adapter platform detection."""
        adapter = OpenAIHandoffAdapter()

        assert adapter.supports_platform("openai")
        assert adapter.supports_platform("openai-compat")
        assert not adapter.supports_platform("anthropic")

    def test_anthropic_adapter_supports_platform(self):
        """Test Anthropic adapter platform detection."""
        adapter = AnthropicHandoffAdapter()

        assert adapter.supports_platform("anthropic")
        assert adapter.supports_platform("claude")
        assert not adapter.supports_platform("openai")

    def test_agdd_adapter_tool_schema(self):
        """Test AGDD adapter tool schema format."""
        adapter = AGDDHandoffAdapter()
        schema = adapter.format_tool_schema()

        assert schema["name"] == "handoff"
        assert "description" in schema
        assert "parameters" in schema
        assert schema["parameters"]["type"] == "object"
        assert "target_agent" in schema["parameters"]["properties"]
        assert "task" in schema["parameters"]["properties"]

    def test_adk_adapter_tool_schema(self):
        """Test ADK adapter tool schema format."""
        adapter = ADKHandoffAdapter()
        schema = adapter.format_tool_schema()

        assert schema["name"] == "handoff"
        assert "input_schema" in schema
        assert schema["input_schema"]["type"] == "object"

    def test_openai_adapter_tool_schema(self):
        """Test OpenAI adapter tool schema format."""
        adapter = OpenAIHandoffAdapter()
        schema = adapter.format_tool_schema()

        assert schema["type"] == "function"
        assert "function" in schema
        assert schema["function"]["name"] == "handoff"
        assert "parameters" in schema["function"]

    def test_anthropic_adapter_tool_schema(self):
        """Test Anthropic adapter tool schema format."""
        adapter = AnthropicHandoffAdapter()
        schema = adapter.format_tool_schema()

        assert schema["name"] == "handoff"
        assert "input_schema" in schema
        assert schema["input_schema"]["type"] == "object"


class TestHandoffTool:
    """Tests for HandoffTool."""

    def test_get_adapter(self, handoff_tool):
        """Test getting adapter by platform."""
        # AGDD adapter
        agdd_adapter = handoff_tool.get_adapter("agdd")
        assert agdd_adapter is not None
        assert isinstance(agdd_adapter, AGDDHandoffAdapter)

        # OpenAI adapter
        openai_adapter = handoff_tool.get_adapter("openai")
        assert openai_adapter is not None
        assert isinstance(openai_adapter, OpenAIHandoffAdapter)

        # Invalid platform
        invalid_adapter = handoff_tool.get_adapter("unknown-platform")
        assert invalid_adapter is None

    def test_get_tool_schema(self, handoff_tool):
        """Test getting tool schema for different platforms."""
        # AGDD schema
        agdd_schema = handoff_tool.get_tool_schema("agdd")
        assert agdd_schema["name"] == "handoff"

        # OpenAI schema
        openai_schema = handoff_tool.get_tool_schema("openai")
        assert openai_schema["type"] == "function"

        # Invalid platform should raise
        with pytest.raises(ValueError, match="Unsupported platform"):
            handoff_tool.get_tool_schema("invalid")

    @pytest.mark.asyncio
    async def test_handoff_basic(self, handoff_tool):
        """Test basic handoff execution."""
        result = await handoff_tool.handoff(
            source_agent="main-agent",
            target_agent="sub-agent",
            task="Process customer inquiry",
            context={"customer_id": "123"},
            platform="agdd",
            run_id="test-run-123",
        )

        assert result["status"] == "completed"
        assert "handoff_id" in result
        assert result["handoff_id"] is not None

    @pytest.mark.asyncio
    async def test_handoff_unsupported_platform(self, handoff_tool):
        """Test handoff with unsupported platform."""
        with pytest.raises(ValueError, match="Unsupported platform"):
            await handoff_tool.handoff(
                source_agent="main-agent",
                target_agent="sub-agent",
                task="Test task",
                platform="unsupported-platform",
            )

    @pytest.mark.asyncio
    async def test_handoff_tracking(self, handoff_tool):
        """Test handoff request tracking."""
        # Execute handoff
        result = await handoff_tool.handoff(
            source_agent="main-agent",
            target_agent="sub-agent",
            task="Test task",
            platform="agdd",
        )

        handoff_id = result["handoff_id"]

        # Retrieve handoff request
        request = handoff_tool.get_handoff(handoff_id)

        assert request is not None
        assert request.handoff_id == handoff_id
        assert request.source_agent == "main-agent"
        assert request.target_agent == "sub-agent"
        assert request.status == "completed"

    @pytest.mark.asyncio
    async def test_list_handoffs(self, handoff_tool):
        """Test listing handoff requests."""
        # Execute multiple handoffs
        await handoff_tool.handoff(
            source_agent="agent-1",
            target_agent="agent-2",
            task="Task 1",
            platform="agdd",
        )

        await handoff_tool.handoff(
            source_agent="agent-1",
            target_agent="agent-3",
            task="Task 2",
            platform="agdd",
        )

        await handoff_tool.handoff(
            source_agent="agent-2",
            target_agent="agent-4",
            task="Task 3",
            platform="agdd",
        )

        # List all handoffs
        all_handoffs = handoff_tool.list_handoffs()
        assert len(all_handoffs) == 3

        # Filter by source agent
        agent1_handoffs = handoff_tool.list_handoffs(source_agent="agent-1")
        assert len(agent1_handoffs) == 2

        # Filter by status
        completed_handoffs = handoff_tool.list_handoffs(status="completed")
        assert len(completed_handoffs) == 3

    @pytest.mark.asyncio
    async def test_handoff_with_permissions_allowed(self, handoff_tool_with_permissions):
        """Test handoff with permission check (allowed)."""
        # This assumes default policy allows handoffs
        # Actual behavior depends on permission evaluator configuration

        result = await handoff_tool_with_permissions.handoff(
            source_agent="test-agent",
            target_agent="sub-agent",
            task="Test task",
            platform="agdd",
            run_id="test-run-123",
        )

        # Should succeed if policy allows
        assert result["status"] == "completed"


@pytest.mark.integration
@pytest.mark.slow
class TestHandoffE2E:
    """End-to-end handoff tests."""

    @pytest.mark.asyncio
    async def test_multi_platform_handoff(self):
        """
        Test handoff across multiple platforms.

        Simulates:
        1. AGDD agent delegates to ADK agent
        2. ADK agent delegates to OpenAI agent
        3. OpenAI agent delegates back to AGDD agent
        """
        handoff_tool = HandoffTool()

        # AGDD → ADK
        result1 = await handoff_tool.handoff(
            source_agent="agdd-main",
            target_agent="adk-specialist",
            task="Analyze customer sentiment",
            platform="adk",
        )

        assert result1["status"] == "completed"

        # ADK → OpenAI
        result2 = await handoff_tool.handoff(
            source_agent="adk-specialist",
            target_agent="openai-assistant",
            task="Generate recommendations",
            platform="openai",
        )

        assert result2["status"] == "completed"

        # OpenAI → AGDD
        result3 = await handoff_tool.handoff(
            source_agent="openai-assistant",
            target_agent="agdd-finalizer",
            task="Format final report",
            platform="agdd",
        )

        assert result3["status"] == "completed"

        # Verify all handoffs tracked
        all_handoffs = handoff_tool.list_handoffs()
        assert len(all_handoffs) == 3

    @pytest.mark.asyncio
    async def test_handoff_with_approval_gate(self):
        """
        Test handoff with approval gate integration.

        This would require:
        1. Permission evaluator configured with REQUIRE_APPROVAL
        2. Approval gate integration
        3. Human approval workflow

        Skipping actual implementation as it requires full setup.
        """
        pytest.skip("Requires approval gate integration")

    @pytest.mark.asyncio
    async def test_handoff_error_handling(self, handoff_tool):
        """Test handoff error handling."""

        # Test with invalid platform
        with pytest.raises(ValueError):
            await handoff_tool.handoff(
                source_agent="test-agent",
                target_agent="target-agent",
                task="Test task",
                platform="invalid-platform",
            )

        # Verify failed handoff is tracked
        failed_handoffs = handoff_tool.list_handoffs(status="failed")

        # Should have one failed handoff
        assert len(failed_handoffs) >= 1
        assert failed_handoffs[0].status == "failed"
        assert failed_handoffs[0].error is not None
