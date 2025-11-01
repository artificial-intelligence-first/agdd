"""Tests for CLI replay functionality."""

from __future__ import annotations

import json
from pathlib import Path


class TestCLIReplay:
    """Tests for agent run --replay flag."""

    def test_replay_extracts_environment_snapshot_from_summary_json(
        self, tmp_path: Path
    ) -> None:
        """Test that replay extracts environment_snapshot from summary.json."""
        # Create a summary.json file with nested environment_snapshot
        summary_file = tmp_path / "summary.json"
        summary_data = {
            "run_id": "mag-12345678",
            "slug": "test-agent",
            "cost_usd": 0.0,
            "token_count": 0,
            "deterministic": True,
            "environment_snapshot": {
                "timestamp": 1234567890.0,
                "seed": 42,
                "deterministic_mode": True,
                "env_vars": {},
            },
        }
        summary_file.write_text(json.dumps(summary_data, indent=2))

        # Read and process replay file (simulating CLI logic)
        replay_data = json.loads(summary_file.read_text())

        # Extract environment_snapshot if present (CLI logic)
        if "environment_snapshot" in replay_data:
            replay_snapshot = replay_data["environment_snapshot"]
        else:
            replay_snapshot = replay_data

        # Verify we extracted the nested snapshot correctly
        assert replay_snapshot["seed"] == 42
        assert replay_snapshot["deterministic_mode"] is True
        assert replay_snapshot["timestamp"] == 1234567890.0
        assert "run_id" not in replay_snapshot  # Should not have summary fields

    def test_replay_uses_raw_snapshot_format_directly(self, tmp_path: Path) -> None:
        """Test that replay works with raw snapshot format (no nesting)."""
        # Create a raw snapshot file (not summary.json format)
        snapshot_file = tmp_path / "snapshot.json"
        snapshot_data = {
            "timestamp": 9876543210.0,
            "seed": 100,
            "deterministic_mode": True,
            "env_vars": {"AGDD_DETERMINISTIC_SEED": "100"},
        }
        snapshot_file.write_text(json.dumps(snapshot_data, indent=2))

        # Read and process replay file (simulating CLI logic)
        replay_data = json.loads(snapshot_file.read_text())

        # Extract environment_snapshot if present
        if "environment_snapshot" in replay_data:
            replay_snapshot = replay_data["environment_snapshot"]
        else:
            replay_snapshot = replay_data

        # Verify we use the raw snapshot directly
        assert replay_snapshot["seed"] == 100
        assert replay_snapshot["deterministic_mode"] is True
        assert replay_snapshot["timestamp"] == 9876543210.0

    def test_replay_from_summary_json_restores_deterministic_state(
        self, tmp_path: Path
    ) -> None:
        """Test end-to-end replay from summary.json restores deterministic state."""
        from agdd.runner_determinism import (
            create_replay_context,
            get_deterministic_mode,
            get_deterministic_seed,
            set_deterministic_mode,
        )

        # Create summary.json with nested snapshot
        summary_file = tmp_path / "summary.json"
        summary_data = {
            "run_id": "mag-87654321",
            "environment_snapshot": {
                "timestamp": 1111111111.0,
                "seed": 999,
                "deterministic_mode": True,
                "env_vars": {},
            },
        }
        summary_file.write_text(json.dumps(summary_data))

        # Start in non-deterministic mode
        set_deterministic_mode(False)

        # Load replay data and extract snapshot (simulating CLI)
        replay_data = json.loads(summary_file.read_text())
        if "environment_snapshot" in replay_data:
            replay_snapshot = replay_data["environment_snapshot"]
        else:
            replay_snapshot = replay_data

        # Create replay context
        context = create_replay_context(replay_snapshot)

        # Verify deterministic state was restored
        assert get_deterministic_mode() is True
        assert get_deterministic_seed() == 999
        assert context["replay_mode"] is True
        assert context["replay_seed"] == 999

    def test_replay_from_nondeterministic_summary_json(self, tmp_path: Path) -> None:
        """Test replay from non-deterministic summary.json clears deterministic mode."""
        from agdd.runner_determinism import (
            create_replay_context,
            get_deterministic_mode,
            set_deterministic_mode,
            set_deterministic_seed,
        )

        # Create summary.json without deterministic mode
        summary_file = tmp_path / "summary.json"
        summary_data = {
            "run_id": "mag-55555555",
            "deterministic": False,
            "environment_snapshot": {
                "timestamp": 2222222222.0,
                "seed": 0,
                "deterministic_mode": False,
                "env_vars": {},
            },
        }
        summary_file.write_text(json.dumps(summary_data))

        # Start in deterministic mode
        set_deterministic_mode(True)
        set_deterministic_seed(777)

        # Load replay data and extract snapshot
        replay_data = json.loads(summary_file.read_text())
        if "environment_snapshot" in replay_data:
            replay_snapshot = replay_data["environment_snapshot"]
        else:
            replay_snapshot = replay_data

        # Create replay context
        context = create_replay_context(replay_snapshot)

        # Verify deterministic mode was cleared
        assert get_deterministic_mode() is False
        assert context["replay_mode"] is True
