"""Integration tests for deterministic execution in agent runner."""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from agdd.runner_determinism import get_deterministic_mode, set_deterministic_mode, set_deterministic_seed


class TestAgentRunnerDeterminism:
    """Integration tests for deterministic mode in AgentRunner."""

    def test_prepare_execution_applies_deterministic_settings(self) -> None:
        """Test that deterministic context triggers settings application."""
        # Import here to avoid circular dependencies
        from agdd.runners.agent_runner import AgentRunner
        from agdd.registry import AgentDescriptor

        # Create a mock agent descriptor
        mock_agent = MagicMock(spec=AgentDescriptor)
        mock_agent.slug = "test-agent"
        mock_agent.name = "TestAgent"
        mock_agent.raw = {
            "provider_config": {
                "temperature": 0.9,
                "top_p": 0.95,
                "model": "test-model",
            }
        }

        # Create runner with mocked dependencies
        runner = AgentRunner()

        # Mock the registry to return our test agent
        with patch.object(runner.registry, "load_agent", return_value=mock_agent):
            # Mock the router to avoid real execution planning
            mock_plan = MagicMock()
            mock_plan.span_context = {}
            mock_plan.enable_otel = False

            with patch.object(runner.router, "get_plan", return_value=mock_plan):
                # Enable deterministic mode
                set_deterministic_mode(True)
                set_deterministic_seed(42)

                # Prepare execution with deterministic context
                context = {"deterministic": True}

                # Call _prepare_execution
                exec_ctx = runner._prepare_execution("test-agent", "run-123", context)

                # Verify that the agent's provider_config was modified
                modified_config = mock_agent.raw["provider_config"]

                # Check deterministic settings were applied
                assert modified_config["temperature"] == 0.0
                assert modified_config["seed"] == 42
                assert modified_config["top_p"] == 1.0
                assert "metadata" in modified_config
                assert modified_config["metadata"]["deterministic_mode"] is True
                assert modified_config["metadata"]["deterministic_seed"] == 42

    def test_prepare_execution_without_deterministic_context(self) -> None:
        """Test that execution without deterministic context leaves config unchanged."""
        from agdd.runners.agent_runner import AgentRunner
        from agdd.registry import AgentDescriptor

        # Create a mock agent descriptor
        original_config = {
            "temperature": 0.9,
            "top_p": 0.95,
            "model": "test-model",
        }
        mock_agent = MagicMock(spec=AgentDescriptor)
        mock_agent.slug = "test-agent"
        mock_agent.name = "TestAgent"
        mock_agent.raw = {"provider_config": original_config.copy()}

        # Create runner
        runner = AgentRunner()

        # Mock dependencies
        with patch.object(runner.registry, "load_agent", return_value=mock_agent):
            mock_plan = MagicMock()
            mock_plan.span_context = {}
            mock_plan.enable_otel = False

            with patch.object(runner.router, "get_plan", return_value=mock_plan):
                # Disable deterministic mode
                set_deterministic_mode(False)

                # Prepare execution WITHOUT deterministic context
                context: Dict[str, Any] = {}

                # Call _prepare_execution
                exec_ctx = runner._prepare_execution("test-agent", "run-123", context)

                # Verify config was not modified (temperature should be unchanged)
                config = mock_agent.raw["provider_config"]
                assert config["temperature"] == 0.9
                assert "seed" not in config or config.get("seed") != 42

    def test_deterministic_mode_propagates_to_observability(self) -> None:
        """Test that deterministic context propagates to ObservabilityLogger."""
        from agdd.runners.agent_runner import AgentRunner
        from agdd.registry import AgentDescriptor

        mock_agent = MagicMock(spec=AgentDescriptor)
        mock_agent.slug = "test-agent"
        mock_agent.name = "TestAgent"
        mock_agent.raw = {"provider_config": {}}

        runner = AgentRunner()

        with patch.object(runner.registry, "load_agent", return_value=mock_agent):
            mock_plan = MagicMock()
            mock_plan.span_context = {}
            mock_plan.enable_otel = False

            with patch.object(runner.router, "get_plan", return_value=mock_plan):
                set_deterministic_mode(True)
                set_deterministic_seed(123)

                # Create context with deterministic flag and snapshot
                context = {
                    "deterministic": True,
                    "environment_snapshot": {"seed": 123, "deterministic_mode": True},
                }

                exec_ctx = runner._prepare_execution("test-agent", "run-123", context)

                # Verify ObservabilityLogger received deterministic info
                obs = exec_ctx.observer
                assert obs._deterministic is True
                assert obs._environment_snapshot is not None
                assert obs._environment_snapshot["seed"] == 123
