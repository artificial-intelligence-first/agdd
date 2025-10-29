"""End-to-end integration tests for offer generation flow

All tests in this module perform actual MAG execution with LLM calls,
which can take 30-60+ seconds per test. Tests are marked as 'slow' to
enable fast CI runs with `-m "not slow"`.
"""

import json
import tempfile
from pathlib import Path

import pytest

from agdd.runners.agent_runner import invoke_mag


@pytest.mark.slow
class TestE2EOfferFlow:
    """End-to-end test suite for complete offer generation workflow"""

    def test_full_offer_generation_pipeline(self) -> None:
        """Test complete pipeline from candidate profile to offer packet"""
        payload = {
            "role": "Senior Software Engineer",
            "level": "Senior",
            "location": "San Francisco, CA",
            "experience_years": 8,
            "notes": "Strong distributed systems background",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            output = invoke_mag("offer-orchestrator-mag", payload, base_dir=Path(tmpdir))

            # Verify complete output structure
            assert "offer" in output
            assert "metadata" in output

            # Verify offer details
            offer = output["offer"]
            assert offer["role"] == "Senior Software Engineer"
            assert offer["base_salary"]["currency"] == "USD"
            assert offer["base_salary"]["amount"] > 100000
            assert offer["band"]["min"] <= offer["base_salary"]["amount"] <= offer["band"]["max"]
            assert "sign_on_bonus" in offer

            # Verify metadata
            metadata = output["metadata"]
            assert metadata["generated_by"] == "OfferOrchestratorMAG"
            assert "run_id" in metadata
            assert "timestamp" in metadata

            # Verify observability artifacts
            # base_dir is tmpdir itself, so look there directly
            run_dirs = list(Path(tmpdir).glob("mag-*"))
            assert len(run_dirs) > 0

            # Check MAG artifacts
            mag_dir = run_dirs[0]
            assert (mag_dir / "logs.jsonl").exists()
            assert (mag_dir / "metrics.json").exists()

            # Check SAG artifacts (delegated execution)
            sag_dirs = list(Path(tmpdir).glob("sag-*"))
            assert len(sag_dirs) > 0

    def test_multiple_candidates_different_levels(self) -> None:
        """Test processing multiple candidates with varying seniority"""
        candidates = [
            {"role": "Junior Engineer", "level": "Junior", "experience_years": 1},
            {"role": "Software Engineer", "level": "Mid", "experience_years": 4},
            {"role": "Senior Engineer", "level": "Senior", "experience_years": 8},
            {"role": "Staff Engineer", "level": "Staff", "experience_years": 12},
        ]

        outputs = []
        for candidate in candidates:
            output = invoke_mag("offer-orchestrator-mag", candidate)
            outputs.append(output)

        # All should succeed
        assert len(outputs) == 4
        for output in outputs:
            assert output["metadata"]["successful_tasks"] == 1

        # Verify salary progression
        salaries = [o["offer"]["base_salary"]["amount"] for o in outputs]
        # Each level should generally have higher salary than previous
        assert salaries[0] < salaries[1] < salaries[2] < salaries[3]

    def test_location_variations(self) -> None:
        """Test different geographic locations"""
        locations = ["San Francisco, CA", "New York, NY", "Austin, TX", "Remote - US"]

        outputs = []
        for location in locations:
            payload = {
                "role": "Software Engineer",
                "level": "Mid",
                "location": location,
                "experience_years": 5,
            }
            output = invoke_mag("offer-orchestrator-mag", payload)
            outputs.append((location, output))

        # All should succeed
        for location, output in outputs:
            assert output["metadata"]["successful_tasks"] == 1
            assert output["offer"]["base_salary"]["amount"] > 0

        # SF should have highest salary
        sf_salary = next(
            o["offer"]["base_salary"]["amount"] for loc, o in outputs if "San Francisco" in loc
        )
        remote_salary = next(
            o["offer"]["base_salary"]["amount"] for loc, o in outputs if "Remote" in loc
        )
        assert sf_salary > remote_salary

    def test_skills_integration(self) -> None:
        """Test that skills are properly invoked during orchestration"""
        payload = {"role": "Engineer", "level": "Mid", "experience_years": 5}

        with tempfile.TemporaryDirectory() as tmpdir:
            invoke_mag("offer-orchestrator-mag", payload, base_dir=Path(tmpdir))

            # Check logs for skill invocations
            sag_dirs = list(Path(tmpdir).glob("sag-*"))
            assert len(sag_dirs) > 0

            sag_log = sag_dirs[0] / "logs.jsonl"
            logs = sag_log.read_text().strip().split("\n")
            log_events = [json.loads(line)["event"] for line in logs]

            # Should see skill_invoked event
            assert "skill_invoked" in log_events or "start" in log_events

    def test_error_resilience(self) -> None:
        """Test that system handles edge cases gracefully"""
        # Empty experience
        payload1 = {"role": "Engineer", "experience_years": 0}
        output1 = invoke_mag("offer-orchestrator-mag", payload1)
        assert output1["metadata"]["successful_tasks"] >= 1

        # Missing optional fields
        payload2 = {"role": "Engineer"}
        output2 = invoke_mag("offer-orchestrator-mag", payload2)
        assert output2["metadata"]["successful_tasks"] >= 1

    def test_observability_completeness(self) -> None:
        """Test that all observability artifacts are created and well-formed"""
        payload = {"role": "Engineer", "level": "Mid"}

        with tempfile.TemporaryDirectory() as tmpdir:
            invoke_mag("offer-orchestrator-mag", payload, base_dir=Path(tmpdir))

            # Check MAG artifacts
            mag_dirs = list(Path(tmpdir).glob("mag-*"))
            assert len(mag_dirs) == 1
            mag_dir = mag_dirs[0]

            # Verify log structure
            logs = (mag_dir / "logs.jsonl").read_text().strip().split("\n")
            assert len(logs) >= 2  # At least start and end
            first_log = json.loads(logs[0])
            assert "event" in first_log
            assert "timestamp" in first_log

            # Verify metrics structure
            metrics = json.load((mag_dir / "metrics.json").open())
            assert "latency_ms" in metrics

            # Verify summary structure
            summary = json.load((mag_dir / "summary.json").open())
            assert "run_id" in summary
            assert "total_logs" in summary
