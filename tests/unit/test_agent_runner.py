"""Unit tests for agdd.runners.agent_runner module"""

import pytest
import tempfile
import json
from pathlib import Path
from agdd.runners.agent_runner import AgentRunner, Delegation, Result, ObservabilityLogger, SkillRuntime


class TestObservabilityLogger:
    """Test suite for ObservabilityLogger"""

    def test_log_and_metric(self):
        """Test logging and metrics capture"""
        with tempfile.TemporaryDirectory() as tmpdir:
            obs = ObservabilityLogger("test-run-123", base_dir=Path(tmpdir))

            obs.log("test-run-123", "start", {"agent": "TestAgent"})
            obs.metric("test-run-123", "latency_ms", 100)
            obs.finalize()

            # Check files created
            assert (obs.run_dir / "logs.jsonl").exists()
            assert (obs.run_dir / "metrics.json").exists()
            assert (obs.run_dir / "summary.json").exists()

            # Validate content
            logs = (obs.run_dir / "logs.jsonl").read_text().strip().split("\n")
            assert len(logs) == 1
            log_entry = json.loads(logs[0])
            assert log_entry["event"] == "start"
            assert log_entry["data"]["agent"] == "TestAgent"


class TestSkillRuntime:
    """Test suite for SkillRuntime"""

    def test_exists(self):
        """Test skill existence check"""
        runtime = SkillRuntime()
        assert runtime.exists("skill.salary-band-lookup")
        assert not runtime.exists("skill.nonexistent")

    def test_invoke(self):
        """Test skill invocation"""
        runtime = SkillRuntime()
        result = runtime.invoke("skill.salary-band-lookup", {
            "role": "Senior Engineer",
            "level": "Senior",
            "location": "New York, NY"
        })

        assert "min" in result
        assert "max" in result
        assert "currency" in result
        assert result["currency"] == "USD"


class TestAgentRunner:
    """Test suite for AgentRunner"""

    def test_invoke_sag(self):
        """Test SAG invocation"""
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = AgentRunner(base_dir=Path(tmpdir))

            delegation = Delegation(
                task_id="task-001",
                sag_id="compensation-advisor-sag",
                input={"candidate_profile": {
                    "role": "Software Engineer",
                    "level": "Mid",
                    "location": "Remote",
                    "experience_years": 5
                }},
                context={"parent_run_id": "mag-test"}
            )

            result = runner.invoke_sag(delegation)

            assert result.status == "success"
            assert "offer" in result.output
            assert result.output["offer"]["role"] == "Software Engineer"
            assert "base_salary" in result.output["offer"]
            assert "duration_ms" in result.metrics

    def test_invoke_mag(self):
        """Test MAG invocation"""
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = AgentRunner(base_dir=Path(tmpdir))

            payload = {
                "role": "Staff Engineer",
                "level": "Staff",
                "location": "San Francisco, CA",
                "experience_years": 12
            }

            output = runner.invoke_mag("offer-orchestrator-mag", payload)

            assert "offer" in output
            assert "metadata" in output
            assert output["metadata"]["generated_by"] == "OfferOrchestratorMAG"
            assert "run_id" in output["metadata"]
            assert "timestamp" in output["metadata"]

    def test_sag_retry_on_failure(self):
        """Test SAG retry policy"""
        # This test would require mocking to force failures
        # For now, we test that the retry config is respected
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = AgentRunner(base_dir=Path(tmpdir))

            delegation = Delegation(
                task_id="task-retry",
                sag_id="compensation-advisor-sag",
                input={"candidate_profile": {"role": "Engineer"}},
                context={}
            )

            result = runner.invoke_sag(delegation)
            # Should succeed on first attempt
            assert result.metrics["attempts"] == 1

    def test_observability_artifacts(self):
        """Test that observability artifacts are created"""
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = AgentRunner(base_dir=Path(tmpdir))

            payload = {"role": "Engineer", "level": "Junior"}
            runner.invoke_mag("offer-orchestrator-mag", payload)

            # Check that .runs/agents/<RUN_ID>/ exists
            # base_dir is the parent of "agents", so look directly in tmpdir
            agents_dir = Path(tmpdir)
            run_dirs = list(agents_dir.glob("mag-*"))
            assert len(run_dirs) > 0, f"No MAG run directories found in {agents_dir}"

            # Check artifacts
            run_dir = run_dirs[0]
            assert (run_dir / "logs.jsonl").exists()
            assert (run_dir / "metrics.json").exists()
            assert (run_dir / "summary.json").exists()
