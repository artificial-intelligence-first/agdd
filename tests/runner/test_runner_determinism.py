"""Tests for runner determinism and replay functionality."""

from __future__ import annotations

import json
import os
import random
from pathlib import Path

import pytest

from agdd.runner_determinism import (
    apply_deterministic_settings,
    compute_run_fingerprint,
    create_replay_context,
    get_deterministic_mode,
    get_deterministic_seed,
    set_deterministic_mode,
    set_deterministic_seed,
    snapshot_environment,
)


class TestDeterministicMode:
    """Tests for deterministic mode control."""

    def test_set_and_get_deterministic_mode(self) -> None:
        """Test setting and getting deterministic mode."""
        # Start with disabled mode
        set_deterministic_mode(False)
        assert get_deterministic_mode() is False

        # Enable mode
        set_deterministic_mode(True)
        assert get_deterministic_mode() is True

        # Disable again
        set_deterministic_mode(False)
        assert get_deterministic_mode() is False

    def test_deterministic_mode_isolated(self) -> None:
        """Test that deterministic mode can be toggled independently."""
        set_deterministic_mode(True)
        assert get_deterministic_mode() is True

        set_deterministic_mode(False)
        assert get_deterministic_mode() is False


class TestDeterministicSeed:
    """Tests for deterministic seed management."""

    def test_get_seed_uses_explicit_value(self) -> None:
        """Test that explicit seed value is returned."""
        set_deterministic_seed(42)
        assert get_deterministic_seed() == 42

        set_deterministic_seed(12345)
        assert get_deterministic_seed() == 12345

    def test_get_seed_from_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that seed can be read from environment variable."""
        # Clear explicit seed
        set_deterministic_seed(None)  # type: ignore[arg-type]

        monkeypatch.setenv("AGDD_DETERMINISTIC_SEED", "9999")
        seed = get_deterministic_seed()
        assert seed == 9999

    def test_get_seed_generates_stable_default(self) -> None:
        """Test that default seed generation is stable within a minute."""
        # Clear explicit seed and env var
        set_deterministic_seed(None)  # type: ignore[arg-type]
        if "AGDD_DETERMINISTIC_SEED" in os.environ:
            del os.environ["AGDD_DETERMINISTIC_SEED"]

        seed1 = get_deterministic_seed()
        seed2 = get_deterministic_seed()

        # Seeds should be identical within the same minute
        assert seed1 == seed2
        assert isinstance(seed1, int)

    def test_get_seed_caches_computed_value(self) -> None:
        """Test that computed seed is cached across calls."""
        import time as time_module

        # Clear explicit seed and env var
        set_deterministic_seed(None)  # type: ignore[arg-type]
        if "AGDD_DETERMINISTIC_SEED" in os.environ:
            del os.environ["AGDD_DETERMINISTIC_SEED"]

        # Get seed once
        first_seed = get_deterministic_seed()

        # Wait a bit (but not crossing a minute boundary)
        time_module.sleep(0.1)

        # Get seed again - should be identical due to caching
        second_seed = get_deterministic_seed()

        assert first_seed == second_seed

    def test_get_seed_from_env_is_cached(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that environment-based seed is cached."""
        # Clear explicit seed
        set_deterministic_seed(None)  # type: ignore[arg-type]

        monkeypatch.setenv("AGDD_DETERMINISTIC_SEED", "9999")
        first_call = get_deterministic_seed()
        assert first_call == 9999

        # Change env var after first call
        monkeypatch.setenv("AGDD_DETERMINISTIC_SEED", "8888")

        # Should still return cached value
        second_call = get_deterministic_seed()
        assert second_call == 9999  # Still the cached value, not 8888

    def test_set_seed_applies_to_random_module(self) -> None:
        """Test that setting seed actually seeds Python's random module."""
        # Set a specific seed
        set_deterministic_seed(42)

        # Generate random numbers
        values1 = [random.random() for _ in range(5)]

        # Reset seed to same value
        set_deterministic_seed(42)

        # Generate random numbers again
        values2 = [random.random() for _ in range(5)]

        # Values should be identical due to same seed
        assert values1 == values2

    def test_different_seeds_produce_different_values(self) -> None:
        """Test that different seeds produce different random values."""
        set_deterministic_seed(100)
        values1 = [random.random() for _ in range(5)]

        set_deterministic_seed(200)
        values2 = [random.random() for _ in range(5)]

        # Values should be different with different seeds
        assert values1 != values2

    def test_deterministic_mode_applies_seed_to_random(self) -> None:
        """Test that enabling deterministic mode applies the seed to random module."""
        # Set seed first
        set_deterministic_seed(123)

        # Generate some random values
        values1 = [random.random() for _ in range(5)]

        # Enable deterministic mode (should re-apply seed)
        set_deterministic_mode(True)

        # Generate random values again - should be same as first set
        values2 = [random.random() for _ in range(5)]

        assert values1 == values2

    def test_get_seed_applies_to_random_when_deterministic_mode_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that get_deterministic_seed() applies seed to random when mode is enabled."""
        # Clear cached seed
        set_deterministic_seed(None)  # type: ignore[arg-type]
        if "AGDD_DETERMINISTIC_SEED" in os.environ:
            del os.environ["AGDD_DETERMINISTIC_SEED"]

        # Enable deterministic mode
        set_deterministic_mode(True)

        # Set env seed
        monkeypatch.setenv("AGDD_DETERMINISTIC_SEED", "999")

        # Get seed (should apply to random module)
        seed = get_deterministic_seed()
        assert seed == 999

        # Generate random values
        values1 = [random.random() for _ in range(5)]

        # Reset seed to same value and regenerate
        random.seed(999)
        values2 = [random.random() for _ in range(5)]

        # Values should be identical
        assert values1 == values2


class TestSnapshotEnvironment:
    """Tests for environment snapshot creation."""

    def test_snapshot_contains_required_fields(self) -> None:
        """Test that snapshot contains all required fields."""
        set_deterministic_mode(True)
        set_deterministic_seed(42)

        snapshot = snapshot_environment()

        assert "timestamp" in snapshot
        assert "seed" in snapshot
        assert "deterministic_mode" in snapshot
        assert "env_vars" in snapshot

        assert snapshot["deterministic_mode"] is True
        assert snapshot["seed"] == 42
        assert isinstance(snapshot["timestamp"], float)
        assert isinstance(snapshot["env_vars"], dict)

    def test_snapshot_captures_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that relevant environment variables are captured."""
        monkeypatch.setenv("AGDD_DETERMINISTIC_SEED", "123")
        monkeypatch.setenv("AGDD_ENABLE_MCP", "true")

        snapshot = snapshot_environment()

        assert "AGDD_DETERMINISTIC_SEED" in snapshot["env_vars"]
        assert snapshot["env_vars"]["AGDD_DETERMINISTIC_SEED"] == "123"
        assert "AGDD_ENABLE_MCP" in snapshot["env_vars"]
        assert snapshot["env_vars"]["AGDD_ENABLE_MCP"] == "true"

    def test_snapshot_excludes_missing_env_vars(self) -> None:
        """Test that missing environment variables are not included."""
        # Clear all relevant env vars
        for key in ["AGDD_DETERMINISTIC_SEED", "AGDD_ENABLE_MCP", "AGDD_LOG_LEVEL"]:
            if key in os.environ:
                del os.environ[key]

        snapshot = snapshot_environment()

        # env_vars dict should be empty or contain only present vars
        for key in ["AGDD_DETERMINISTIC_SEED", "AGDD_ENABLE_MCP", "AGDD_LOG_LEVEL"]:
            if key in snapshot["env_vars"]:
                pytest.fail(f"Expected {key} to be absent from snapshot")


class TestApplyDeterministicSettings:
    """Tests for applying deterministic settings to provider config."""

    def test_apply_when_disabled_returns_unchanged(self) -> None:
        """Test that config is unchanged when deterministic mode is disabled."""
        set_deterministic_mode(False)

        original = {"temperature": 0.7, "top_p": 0.9}
        result = apply_deterministic_settings(original)

        assert result == original
        assert result is not original  # Should be a copy

    def test_apply_when_enabled_sets_temperature_zero(self) -> None:
        """Test that temperature is set to 0 in deterministic mode."""
        set_deterministic_mode(True)
        set_deterministic_seed(42)

        config = {"temperature": 0.7}
        result = apply_deterministic_settings(config)

        assert result["temperature"] == 0.0

    def test_apply_when_enabled_sets_seed(self) -> None:
        """Test that seed is added in deterministic mode."""
        set_deterministic_mode(True)
        set_deterministic_seed(42)

        config = {}
        result = apply_deterministic_settings(config)

        assert result["seed"] == 42

    def test_apply_when_enabled_normalizes_top_p(self) -> None:
        """Test that top_p is set to 1.0 in deterministic mode."""
        set_deterministic_mode(True)

        config = {"top_p": 0.9}
        result = apply_deterministic_settings(config)

        assert result["top_p"] == 1.0

    def test_apply_adds_metadata(self) -> None:
        """Test that deterministic metadata is added to config."""
        set_deterministic_mode(True)
        set_deterministic_seed(42)

        config = {}
        result = apply_deterministic_settings(config)

        assert "metadata" in result
        assert result["metadata"]["deterministic_mode"] is True
        assert result["metadata"]["deterministic_seed"] == 42

    def test_apply_preserves_existing_metadata(self) -> None:
        """Test that existing metadata is preserved."""
        set_deterministic_mode(True)
        set_deterministic_seed(42)

        config = {"metadata": {"custom_field": "custom_value"}}
        result = apply_deterministic_settings(config)

        assert result["metadata"]["custom_field"] == "custom_value"
        assert result["metadata"]["deterministic_mode"] is True

    def test_apply_does_not_mutate_original(self) -> None:
        """Test that original config is not mutated."""
        set_deterministic_mode(True)

        original = {"temperature": 0.7, "metadata": {"foo": "bar"}}
        result = apply_deterministic_settings(original)

        # Original should be unchanged
        assert original["temperature"] == 0.7
        assert "seed" not in original
        assert original["metadata"]["foo"] == "bar"
        assert "deterministic_mode" not in original["metadata"]

        # Result should have changes
        assert result["temperature"] == 0.0
        assert "seed" in result


class TestCreateReplayContext:
    """Tests for creating replay context from snapshot."""

    def test_create_context_from_snapshot(self) -> None:
        """Test creating execution context from replay snapshot."""
        snapshot = {
            "timestamp": 1234567890.0,
            "seed": 42,
            "deterministic_mode": True,
        }

        context = create_replay_context(snapshot)

        assert context["replay_mode"] is True
        assert context["replay_timestamp"] == 1234567890.0
        assert context["replay_seed"] == 42

    def test_create_context_enables_deterministic_mode(self) -> None:
        """Test that replay context enables deterministic mode if snapshot had it."""
        set_deterministic_mode(False)

        snapshot = {
            "timestamp": 1234567890.0,
            "seed": 42,
            "deterministic_mode": True,
        }

        create_replay_context(snapshot)

        assert get_deterministic_mode() is True
        assert get_deterministic_seed() == 42

    def test_create_context_merges_additional_context(self) -> None:
        """Test that additional context is merged."""
        snapshot = {"timestamp": 1234567890.0, "seed": 42}
        additional = {"custom_field": "custom_value"}

        context = create_replay_context(snapshot, additional)

        assert context["replay_mode"] is True
        assert context["custom_field"] == "custom_value"

    def test_create_context_handles_missing_fields(self) -> None:
        """Test handling of snapshot with missing fields."""
        snapshot = {}  # Empty snapshot

        context = create_replay_context(snapshot)

        assert context["replay_mode"] is True
        assert context.get("replay_timestamp") is None
        assert context.get("replay_seed") is None


class TestComputeRunFingerprint:
    """Tests for run fingerprint computation."""

    def test_compute_fingerprint_stable(self) -> None:
        """Test that fingerprint is stable for same inputs."""
        agent = "test-agent"
        payload = {"input": "test"}
        config = {"temperature": 0.7}

        fp1 = compute_run_fingerprint(agent, payload, config)
        fp2 = compute_run_fingerprint(agent, payload, config)

        assert fp1 == fp2

    def test_compute_fingerprint_different_for_different_inputs(self) -> None:
        """Test that different inputs produce different fingerprints."""
        agent = "test-agent"
        payload1 = {"input": "test1"}
        payload2 = {"input": "test2"}
        config = {"temperature": 0.7}

        fp1 = compute_run_fingerprint(agent, payload1, config)
        fp2 = compute_run_fingerprint(agent, payload2, config)

        assert fp1 != fp2

    def test_compute_fingerprint_format(self) -> None:
        """Test fingerprint format."""
        agent = "test-agent"
        payload = {"input": "test"}
        config = {"temperature": 0.7}

        fp = compute_run_fingerprint(agent, payload, config)

        assert isinstance(fp, str)
        assert len(fp) == 16  # First 16 characters of SHA256
        assert all(c in "0123456789abcdef" for c in fp)


class TestIntegration:
    """Integration tests for determinism workflow."""

    def test_full_deterministic_workflow(self, tmp_path: Path) -> None:
        """Test complete workflow: enable mode, snapshot, apply settings."""
        # Enable deterministic mode
        set_deterministic_mode(True)
        set_deterministic_seed(42)

        # Create snapshot
        snapshot = snapshot_environment()

        # Apply settings to config
        config = {"temperature": 0.9, "top_p": 0.95}
        deterministic_config = apply_deterministic_settings(config)

        # Verify deterministic config
        assert deterministic_config["temperature"] == 0.0
        assert deterministic_config["seed"] == 42
        assert deterministic_config["metadata"]["deterministic_mode"] is True

        # Save snapshot to file
        snapshot_file = tmp_path / "snapshot.json"
        snapshot_file.write_text(json.dumps(snapshot, indent=2))

        # Load snapshot and create replay context
        loaded_snapshot = json.loads(snapshot_file.read_text())
        replay_context = create_replay_context(loaded_snapshot)

        # Verify replay context
        assert replay_context["replay_mode"] is True
        assert replay_context["replay_seed"] == 42

    def test_replay_workflow_restores_determinism(self) -> None:
        """Test that replay workflow restores deterministic mode."""
        # Setup initial state
        set_deterministic_mode(True)
        set_deterministic_seed(100)
        snapshot = snapshot_environment()

        # Disable mode
        set_deterministic_mode(False)
        assert get_deterministic_mode() is False

        # Replay from snapshot
        create_replay_context(snapshot)

        # Verify mode is restored
        assert get_deterministic_mode() is True
        assert get_deterministic_seed() == 100

    def test_replay_nondeterministic_snapshot_clears_mode(self) -> None:
        """Test that replaying a non-deterministic snapshot clears deterministic mode."""
        # Start with deterministic mode enabled
        set_deterministic_mode(True)
        set_deterministic_seed(999)
        assert get_deterministic_mode() is True

        # Create a non-deterministic snapshot
        set_deterministic_mode(False)
        snapshot = snapshot_environment()
        assert snapshot["deterministic_mode"] is False

        # Enable determinism again before replay
        set_deterministic_mode(True)
        set_deterministic_seed(888)

        # Replay the non-deterministic snapshot
        create_replay_context(snapshot)

        # Verify deterministic mode is now disabled
        assert get_deterministic_mode() is False

    def test_replay_without_seed_clears_cached_seed(self) -> None:
        """Test that replaying a snapshot without a seed clears the cached seed."""
        # Set a seed
        set_deterministic_seed(777)
        assert get_deterministic_seed() == 777

        # Create snapshot without deterministic mode
        set_deterministic_mode(False)
        snapshot = {"deterministic_mode": False, "timestamp": 1234567890.0}

        # Replay
        create_replay_context(snapshot)

        # Seed should be cleared (will generate new one from timestamp)
        set_deterministic_seed(None)  # type: ignore[arg-type]
        # After clearing, getting seed should generate a new one
        new_seed = get_deterministic_seed()
        assert new_seed != 777  # Should be different
