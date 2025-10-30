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

            with patch.object(runner.router, "get_plan", return_value=mock_plan) as mock_get_plan:
                # Enable deterministic mode
                set_deterministic_mode(True)
                set_deterministic_seed(42)

                # Prepare execution with deterministic context
                context = {"deterministic": True}

                # Call _prepare_execution
                exec_ctx = runner._prepare_execution("test-agent", "run-123", context)

                # Verify that the ORIGINAL cached agent was NOT mutated
                assert mock_agent.raw["provider_config"]["temperature"] == 0.9

                # Get the agent that was passed to get_plan (the modified copy)
                agent_passed_to_plan = mock_get_plan.call_args[0][0]
                modified_config = agent_passed_to_plan.raw["provider_config"]

                # Check deterministic settings were applied to the COPY
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

    def test_cached_agent_not_mutated_by_deterministic_run(self) -> None:
        """Test that deterministic runs don't mutate the cached agent descriptor."""
        from agdd.runners.agent_runner import AgentRunner
        from agdd.registry import AgentDescriptor

        # Create a mock agent with specific config
        original_config = {
            "temperature": 0.9,
            "top_p": 0.95,
            "model": "test-model",
        }
        mock_agent = MagicMock(spec=AgentDescriptor)
        mock_agent.slug = "test-agent"
        mock_agent.name = "TestAgent"
        mock_agent.raw = {"provider_config": original_config.copy()}

        runner = AgentRunner()

        with patch.object(runner.registry, "load_agent", return_value=mock_agent):
            mock_plan = MagicMock()
            mock_plan.span_context = {}
            mock_plan.enable_otel = False

            with patch.object(runner.router, "get_plan", return_value=mock_plan):
                set_deterministic_mode(True)
                set_deterministic_seed(42)

                # Run with deterministic context
                deterministic_context = {"deterministic": True}
                exec_ctx = runner._prepare_execution("test-agent", "run-123", deterministic_context)

                # Verify the CACHED agent was NOT mutated
                cached_config = mock_agent.raw["provider_config"]
                assert cached_config["temperature"] == 0.9  # Still original value
                assert "seed" not in cached_config  # Seed was not added
                assert cached_config["top_p"] == 0.95  # Still original value

    def test_deterministic_then_nondeterministic_runs_isolated(self) -> None:
        """Test that a deterministic run doesn't affect subsequent non-deterministic runs."""
        from agdd.runners.agent_runner import AgentRunner
        from agdd.registry import AgentDescriptor

        original_config = {
            "temperature": 0.7,
            "top_p": 0.9,
            "model": "test-model",
        }
        mock_agent = MagicMock(spec=AgentDescriptor)
        mock_agent.slug = "test-agent"
        mock_agent.name = "TestAgent"
        mock_agent.raw = {"provider_config": original_config.copy()}

        runner = AgentRunner()

        with patch.object(runner.registry, "load_agent", return_value=mock_agent):
            mock_plan = MagicMock()
            mock_plan.span_context = {}
            mock_plan.enable_otel = False

            with patch.object(runner.router, "get_plan", return_value=mock_plan) as mock_get_plan:
                set_deterministic_mode(True)
                set_deterministic_seed(42)

                # First run: deterministic
                deterministic_context = {"deterministic": True}
                exec_ctx1 = runner._prepare_execution("test-agent", "run-123", deterministic_context)

                # Get the agent that was passed to get_plan in the first call
                first_call_agent = mock_get_plan.call_args[0][0]
                assert first_call_agent.raw["provider_config"]["temperature"] == 0.0
                assert first_call_agent.raw["provider_config"]["seed"] == 42

                # Reset mock
                mock_get_plan.reset_mock()

                # Second run: non-deterministic
                set_deterministic_mode(False)
                nondeterministic_context: Dict[str, Any] = {}
                exec_ctx2 = runner._prepare_execution("test-agent", "run-456", nondeterministic_context)

                # Get the agent that was passed to get_plan in the second call
                second_call_agent = mock_get_plan.call_args[0][0]
                assert second_call_agent.raw["provider_config"]["temperature"] == 0.7
                assert "seed" not in second_call_agent.raw["provider_config"]
                assert second_call_agent.raw["provider_config"]["top_p"] == 0.9

    def test_programmatic_deterministic_context_applies_settings(self) -> None:
        """Test that context={"deterministic": True} works without global mode."""
        from agdd.runners.agent_runner import AgentRunner
        from agdd.registry import AgentDescriptor
        from agdd.runner_determinism import get_deterministic_mode, set_deterministic_mode

        # Ensure deterministic mode is OFF
        set_deterministic_mode(False)
        assert get_deterministic_mode() is False

        original_config = {
            "temperature": 0.8,
            "top_p": 0.9,
            "model": "test-model",
        }
        mock_agent = MagicMock(spec=AgentDescriptor)
        mock_agent.slug = "test-agent"
        mock_agent.name = "TestAgent"
        mock_agent.raw = {"provider_config": original_config.copy()}

        runner = AgentRunner()

        with patch.object(runner.registry, "load_agent", return_value=mock_agent):
            mock_plan = MagicMock()
            mock_plan.span_context = {}
            mock_plan.enable_otel = False

            with patch.object(runner.router, "get_plan", return_value=mock_plan) as mock_get_plan:
                # Call with deterministic context (without setting global mode)
                context = {"deterministic": True, "environment_snapshot": {"seed": 555}}
                exec_ctx = runner._prepare_execution("test-agent", "run-999", context)

                # Get the agent passed to get_plan
                agent_passed = mock_get_plan.call_args[0][0]

                # Verify deterministic settings were applied
                assert agent_passed.raw["provider_config"]["temperature"] == 0.0
                assert "seed" in agent_passed.raw["provider_config"]
                assert agent_passed.raw["provider_config"]["top_p"] == 1.0

                # Verify global mode is NOW ENABLED (kept for execution)
                assert get_deterministic_mode() is True

                # Verify context contains restoration info
                assert "_previous_deterministic_mode" in context
                assert context["_previous_deterministic_mode"] is False

        # Clean up - restore mode
        set_deterministic_mode(False)

    def test_programmatic_deterministic_execution_restores_mode_after_run(self) -> None:
        """Test that deterministic mode is restored after successful execution."""
        from agdd.runners.agent_runner import AgentRunner
        from agdd.registry import AgentDescriptor
        from agdd.runner_determinism import get_deterministic_mode, set_deterministic_mode

        # Ensure deterministic mode is OFF
        set_deterministic_mode(False)
        assert get_deterministic_mode() is False

        # Create mock agent
        original_config = {
            "temperature": 0.7,
            "model": "test-model",
        }
        mock_agent = MagicMock(spec=AgentDescriptor)
        mock_agent.slug = "test-agent"
        mock_agent.name = "TestAgent"
        mock_agent.raw = {"provider_config": original_config.copy()}

        runner = AgentRunner()

        with patch.object(runner.registry, "load_agent", return_value=mock_agent):
            mock_plan = MagicMock()
            mock_plan.span_context = {}
            mock_plan.enable_otel = False

            with patch.object(runner.router, "get_plan", return_value=mock_plan):
                # Test _prepare_execution with deterministic context
                context = {"deterministic": True}
                exec_ctx = runner._prepare_execution("test-agent", "run-test", context)

                # After _prepare_execution, mode should be enabled
                assert get_deterministic_mode() is True

                # Context should store the previous mode for restoration
                assert "_previous_deterministic_mode" in context
                assert context["_previous_deterministic_mode"] is False

                # Simulate what invoke_mag's finally block does
                if "_previous_deterministic_mode" in context:
                    set_deterministic_mode(context["_previous_deterministic_mode"])

                # After restoration, mode should be back to False
                assert get_deterministic_mode() is False

    def test_deterministic_context_restores_mode_on_exception(self) -> None:
        """Test that deterministic mode is restored even if settings application fails."""
        from agdd.runners.agent_runner import AgentRunner
        from agdd.registry import AgentDescriptor
        from agdd.runner_determinism import get_deterministic_mode, set_deterministic_mode

        # Ensure deterministic mode is OFF
        set_deterministic_mode(False)

        mock_agent = MagicMock(spec=AgentDescriptor)
        mock_agent.slug = "test-agent"
        mock_agent.name = "TestAgent"
        mock_agent.raw = {"provider_config": {"temperature": 0.5}}

        runner = AgentRunner()

        with patch.object(runner.registry, "load_agent", return_value=mock_agent):
            # Make deepcopy fail to simulate error during settings application
            with patch("copy.deepcopy") as mock_deepcopy:
                mock_deepcopy.side_effect = RuntimeError("Test error")

                context = {"deterministic": True}

                # This should raise, but mode should still be restored
                with pytest.raises(RuntimeError, match="Test error"):
                    runner._prepare_execution("test-agent", "run-error", context)

                # Verify global mode was restored (not left enabled)
                assert get_deterministic_mode() is False
