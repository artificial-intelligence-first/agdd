"""Unit tests for magsag.runners.agent_runner module"""

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, cast

import pytest

import magsag.observability.cost_tracker as cost_tracker
from magsag.core.memory import MemoryEntry, MemoryScope
from magsag.runners.agent_runner import AgentRunner, Delegation, ObservabilityLogger, SkillRuntime
from magsag.storage.memory_store import SQLiteMemoryStore
from magsag.routing.handoff_tool import HandoffTool

pytestmark = pytest.mark.slow


class TestObservabilityLogger:
    """Test suite for ObservabilityLogger"""

    def test_log_and_metric(self) -> None:
        """Test logging and metrics capture"""
        with tempfile.TemporaryDirectory() as tmpdir:
            obs = ObservabilityLogger("test-run-123", base_dir=Path(tmpdir))

            obs.log("start", {"agent": "TestAgent"})
            obs.metric("latency_ms", 100)
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

    def test_exists(self) -> None:
        """Test skill existence check"""
        runtime = SkillRuntime()
        assert runtime.exists("skill.salary-band-lookup")
        assert not runtime.exists("skill.nonexistent")

    def test_invoke(self) -> None:
        """Test skill invocation"""
        runtime = SkillRuntime()
        result = runtime.invoke(
            "skill.salary-band-lookup",
            {"role": "Senior Engineer", "level": "Senior", "location": "New York, NY"},
        )

        assert "min" in result
        assert "max" in result
        assert "currency" in result
        assert result["currency"] == "USD"


class TestAgentRunner:
    """Test suite for AgentRunner"""

    def test_invoke_sag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test SAG invocation"""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)
            monkeypatch.setattr(cost_tracker, "_tracker", None)

            runner = AgentRunner(base_dir=Path(tmpdir))

            delegation = Delegation(
                task_id="task-001",
                sag_id="compensation-advisor-sag",
                input={
                    "candidate_profile": {
                        "role": "Software Engineer",
                        "level": "Mid",
                        "location": "Remote",
                        "experience_years": 5,
                    }
                },
                context={"parent_run_id": "mag-test"},
            )

            result = runner.invoke_sag(delegation)

            assert result.status == "success"
            assert "offer" in result.output
            assert result.output["offer"]["role"] == "Software Engineer"
            assert "base_salary" in result.output["offer"]
            assert "duration_ms" in result.metrics
            assert "llm_plan" in result.metrics
            assert isinstance(result.metrics["llm_plan"], dict)

            if cost_tracker._tracker is not None:
                cost_tracker._tracker.close()
                cost_tracker._tracker = None

    def test_invoke_mag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test MAG invocation"""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)
            monkeypatch.setattr(cost_tracker, "_tracker", None)

            runner = AgentRunner(base_dir=Path(tmpdir))

            payload = {
                "role": "Staff Engineer",
                "level": "Staff",
                "location": "San Francisco, CA",
                "experience_years": 12,
            }

            output = runner.invoke_mag("offer-orchestrator-mag", payload)

            assert "offer" in output
            assert "metadata" in output
            assert output["metadata"]["generated_by"] == "OfferOrchestratorMAG"
            assert "run_id" in output["metadata"]
            assert "timestamp" in output["metadata"]

            if cost_tracker._tracker is not None:
                cost_tracker._tracker.close()
                cost_tracker._tracker = None

    def test_sag_retry_on_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test SAG retry policy"""
        # This test would require mocking to force failures
        # For now, we test that the retry config is respected
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)
            monkeypatch.setattr(cost_tracker, "_tracker", None)

            runner = AgentRunner(base_dir=Path(tmpdir))

            delegation = Delegation(
                task_id="task-retry",
                sag_id="compensation-advisor-sag",
                input={"candidate_profile": {"role": "Engineer"}},
                context={},
            )

            result = runner.invoke_sag(delegation)
            # Should succeed on first attempt
            assert result.metrics["attempts"] == 1

            if cost_tracker._tracker is not None:
                cost_tracker._tracker.close()
                cost_tracker._tracker = None

    def test_observability_artifacts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that observability artifacts are created"""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)
            monkeypatch.setattr(cost_tracker, "_tracker", None)

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

            if cost_tracker._tracker is not None:
                cost_tracker._tracker.close()
                cost_tracker._tracker = None

    def test_runner_records_costs(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Runner should write cost tracking artifacts under .runs/costs."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(cost_tracker, "_tracker", None)

        runner = AgentRunner()
        payload = {
            "role": "Staff Engineer",
            "level": "Staff",
            "location": "San Francisco, CA",
            "experience_years": 12,
        }
        runner.invoke_mag("offer-orchestrator-mag", payload)

        costs_dir = tmp_path / ".runs" / "costs"
        jsonl_path = costs_dir / "costs.jsonl"
        db_path = tmp_path / ".runs" / "costs.db"

        assert costs_dir.exists()
        assert jsonl_path.exists()
        assert db_path.exists()

        entries = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
        assert entries
        record = json.loads(entries[-1])
        assert record["agent"] == "offer-orchestrator-mag"
        assert "model" in record
        assert record["metadata"].get("placeholder") is True

        if cost_tracker._tracker is not None:
            cost_tracker._tracker.close()
            cost_tracker._tracker = None

    def test_memory_capture_for_mag(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """MAG execution should persist session memories when enabled."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(cost_tracker, "_tracker", None)

        async def run_test() -> list[MemoryEntry]:
            store = SQLiteMemoryStore(db_path=tmp_path / "memory.db", enable_fts=False)
            await store.initialize()
            try:
                runner = AgentRunner(
                    base_dir=tmp_path,
                    enable_memory=True,
                    memory_store=store,
                )
                payload = {
                    "role": "Staff Engineer",
                    "level": "Staff",
                    "location": "Remote",
                    "experience_years": 10,
                }
                runner.invoke_mag("offer-orchestrator-mag", payload)
                memories = await store.list_memories(
                    scope=MemoryScope.SESSION,
                    agent_slug="offer-orchestrator-mag",
                )
            finally:
                await store.close()
            return memories

        memories = asyncio.run(run_test())
        keys = {entry.key for entry in memories}
        assert "input" in keys
        assert "output" in keys

    @pytest.mark.asyncio
    async def test_runner_handoff_wrapper(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """runner.handoff should delegate to configured handoff tool."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(cost_tracker, "_tracker", None)

        class DummyHandoffTool:
            def __init__(self) -> None:
                self.calls: list[dict[str, Any]] = []

            async def handoff(self, **kwargs: Any) -> Dict[str, Any]:
                self.calls.append(kwargs)
                return {
                    "handoff_id": "dummy-handoff",
                    "status": "completed",
                    "result": {"status": "success"},
                }

        tool = DummyHandoffTool()
        runner = AgentRunner(base_dir=tmp_path, handoff_tool=cast(HandoffTool, tool))

        result = await runner.handoff(
            source_agent="alpha-mag",
            target_agent="beta-mag",
            task="Process escalation",
            context={"run_id": "run-alpha"},
        )

        assert result["status"] == "completed"
        assert tool.calls
        call_args = tool.calls[0]
        assert call_args["source_agent"] == "alpha-mag"
        assert call_args["target_agent"] == "beta-mag"
