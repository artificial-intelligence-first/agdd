"""Tests for cost tracker with JSONL and SQLite backends."""

from __future__ import annotations

import json
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import pytest

from agdd.observability.cost_tracker import (
    DEFAULT_COSTS_DIR,
    DEFAULT_DB_PATH,
    DEFAULT_JSONL_PATH,
    CostRecord,
    CostSummary,
    CostTracker,
    get_tracker,
    record_llm_cost,
)


@pytest.fixture
def temp_dir() -> Iterator[Path]:
    """Create temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def tracker(temp_dir: Path) -> Iterator[CostTracker]:
    """Create cost tracker with temporary paths."""
    tracker = CostTracker(
        jsonl_path=temp_dir / "costs.jsonl",
        db_path=temp_dir / "costs.db",
        enable_sqlite=True,
    )
    tracker.initialize()
    yield tracker
    tracker.close()


def test_cost_record_serialization() -> None:
    """Test CostRecord to/from dict conversion."""
    record = CostRecord(
        timestamp="2025-01-01T00:00:00Z",
        model="gpt-4",
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        cost_usd=0.015,
        run_id="run-123",
        step="step-1",
        agent="test-agent",
        metadata={"key": "value"},
    )

    # Serialize and deserialize
    data = record.to_dict()
    restored = CostRecord.from_dict(data)

    assert restored.timestamp == record.timestamp
    assert restored.model == record.model
    assert restored.input_tokens == record.input_tokens
    assert restored.output_tokens == record.output_tokens
    assert restored.total_tokens == record.total_tokens
    assert restored.cost_usd == record.cost_usd
    assert restored.run_id == record.run_id
    assert restored.step == record.step
    assert restored.agent == record.agent
    assert restored.metadata == record.metadata


def test_record_cost_jsonl(tracker: CostTracker, temp_dir: Path) -> None:
    """Test recording costs to JSONL."""
    record = CostRecord(
        timestamp="2025-01-01T00:00:00Z",
        model="claude-3-opus",
        input_tokens=200,
        output_tokens=100,
        total_tokens=300,
        cost_usd=0.03,
    )

    tracker.record_cost(record)

    # Verify JSONL file
    jsonl_path = temp_dir / "costs.jsonl"
    assert jsonl_path.exists()

    with jsonl_path.open("r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["model"] == "claude-3-opus"
        assert data["cost_usd"] == 0.03


def test_record_cost_sqlite(tracker: CostTracker) -> None:
    """Test recording costs to SQLite."""
    record = CostRecord(
        timestamp="2025-01-01T00:00:00Z",
        model="gpt-4-turbo",
        input_tokens=500,
        output_tokens=200,
        total_tokens=700,
        cost_usd=0.07,
        run_id="run-456",
        agent="agent-1",
    )

    tracker.record_cost(record)

    # Verify SQLite
    summary = tracker.get_summary()
    assert summary.total_calls == 1
    assert summary.total_cost_usd == 0.07
    assert summary.total_tokens == 700
    assert "gpt-4-turbo" in summary.by_model
    assert "agent-1" in summary.by_agent


def test_get_summary_filtering(tracker: CostTracker) -> None:
    """Test summary with time and agent filters."""
    base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    # Record multiple entries
    for i in range(5):
        timestamp = (base_time + timedelta(hours=i)).isoformat()
        agent = f"agent-{i % 2}"  # Alternate between agent-0 and agent-1

        record = CostRecord(
            timestamp=timestamp,
            model=f"model-{i}",
            input_tokens=100 * (i + 1),
            output_tokens=50 * (i + 1),
            total_tokens=150 * (i + 1),
            cost_usd=0.01 * (i + 1),
            agent=agent,
        )
        tracker.record_cost(record)

    # All records
    summary = tracker.get_summary()
    assert summary.total_calls == 5
    assert summary.total_cost_usd == pytest.approx(0.15)  # 0.01 + 0.02 + 0.03 + 0.04 + 0.05

    # Filter by time range
    start_time = (base_time + timedelta(hours=2)).isoformat()
    end_time = (base_time + timedelta(hours=4)).isoformat()
    summary = tracker.get_summary(start_time=start_time, end_time=end_time)
    assert summary.total_calls == 3  # Hours 2, 3, 4

    # Filter by agent
    summary = tracker.get_summary(agent="agent-0")
    assert summary.total_calls == 3  # Indices 0, 2, 4


def test_summary_aggregation_by_model(tracker: CostTracker) -> None:
    """Test cost aggregation by model."""
    models = ["gpt-4", "gpt-4", "claude-3-opus", "gpt-4"]
    costs = [0.01, 0.02, 0.03, 0.04]

    for model, cost in zip(models, costs):
        record = CostRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            model=model,
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            cost_usd=cost,
        )
        tracker.record_cost(record)

    summary = tracker.get_summary()
    assert summary.total_calls == 4
    assert summary.total_cost_usd == pytest.approx(0.10)

    # Check by_model aggregation
    assert "gpt-4" in summary.by_model
    assert "claude-3-opus" in summary.by_model
    assert summary.by_model["gpt-4"]["calls"] == 3
    assert summary.by_model["gpt-4"]["cost_usd"] == pytest.approx(0.07)
    assert summary.by_model["claude-3-opus"]["calls"] == 1
    assert summary.by_model["claude-3-opus"]["cost_usd"] == pytest.approx(0.03)


def test_concurrent_writes(temp_dir: Path) -> None:
    """Test thread-safe concurrent cost recording."""
    tracker = CostTracker(
        jsonl_path=temp_dir / "costs.jsonl",
        db_path=temp_dir / "costs.db",
        enable_sqlite=True,
    )
    tracker.initialize()

    num_threads = 10
    records_per_thread = 20
    threads = []

    def record_costs(thread_id: int) -> None:
        """Record costs from a thread."""
        for i in range(records_per_thread):
            record = CostRecord(
                timestamp=datetime.now(timezone.utc).isoformat(),
                model=f"model-{thread_id}",
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
                cost_usd=0.01,
                agent=f"agent-{thread_id}",
            )
            tracker.record_cost(record)

    # Start threads
    for tid in range(num_threads):
        thread = threading.Thread(target=record_costs, args=(tid,))
        threads.append(thread)
        thread.start()

    # Wait for completion
    for thread in threads:
        thread.join()

    # Verify all records were written
    summary = tracker.get_summary()
    expected_total = num_threads * records_per_thread
    assert summary.total_calls == expected_total
    assert summary.total_cost_usd == pytest.approx(expected_total * 0.01)

    # Verify JSONL integrity
    jsonl_path = temp_dir / "costs.jsonl"
    with jsonl_path.open("r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) == expected_total
        # Ensure all lines are valid JSON
        for line in lines:
            data = json.loads(line)
            assert "model" in data
            assert "cost_usd" in data

    tracker.close()


def test_fallback_to_jsonl_when_sqlite_disabled(temp_dir: Path) -> None:
    """Test that tracker falls back to JSONL when SQLite is disabled."""
    tracker = CostTracker(
        jsonl_path=temp_dir / "costs.jsonl",
        db_path=temp_dir / "costs.db",
        enable_sqlite=False,
    )
    tracker.initialize()

    # Record some costs
    for i in range(3):
        record = CostRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            model=f"model-{i}",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            cost_usd=0.01 * (i + 1),
        )
        tracker.record_cost(record)

    # Summary should work via JSONL fallback
    summary = tracker.get_summary()
    assert summary.total_calls == 3
    assert summary.total_cost_usd == pytest.approx(0.06)

    # SQLite db should not exist
    db_path = temp_dir / "costs.db"
    assert not db_path.exists()

    tracker.close()


def test_record_llm_cost_convenience_function(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test convenience function for recording LLM costs."""
    # Override global tracker path
    tracker = CostTracker(
        jsonl_path=temp_dir / "costs.jsonl",
        db_path=temp_dir / "costs.db",
        enable_sqlite=True,
    )
    tracker.initialize()

    # Monkey-patch the global tracker
    import agdd.observability.cost_tracker as ct_module

    monkeypatch.setattr(ct_module, "_tracker", tracker)

    # Use convenience function
    record_llm_cost(
        model="gpt-4",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.015,
        run_id="run-789",
        step="step-1",
        agent="test-agent",
        metadata={"experiment": "test"},
    )

    # Verify
    summary = tracker.get_summary()
    assert summary.total_calls == 1
    assert summary.total_cost_usd == pytest.approx(0.015)

    tracker.close()


def test_empty_database_returns_zero_summary(tracker: CostTracker) -> None:
    """Test that empty database returns zero-valued summary."""
    summary = tracker.get_summary()
    assert summary.total_calls == 0
    assert summary.total_cost_usd == 0.0
    assert summary.total_tokens == 0
    assert len(summary.by_model) == 0
    assert len(summary.by_agent) == 0


def test_summary_excludes_null_agents(tracker: CostTracker) -> None:
    """Test that summary excludes records with null agents from by_agent aggregation."""
    # Record with agent
    record1 = CostRecord(
        timestamp=datetime.now(timezone.utc).isoformat(),
        model="model-1",
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        cost_usd=0.01,
        agent="agent-1",
    )
    tracker.record_cost(record1)

    # Record without agent
    record2 = CostRecord(
        timestamp=datetime.now(timezone.utc).isoformat(),
        model="model-2",
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        cost_usd=0.02,
        agent=None,
    )
    tracker.record_cost(record2)

    summary = tracker.get_summary()
    assert summary.total_calls == 2
    assert len(summary.by_agent) == 1
    assert "agent-1" in summary.by_agent


def test_concurrent_summary_reads_with_writes_jsonl_mode(temp_dir: Path) -> None:
    """Test that concurrent summary reads don't race with writes in JSONL mode."""
    tracker = CostTracker(
        jsonl_path=temp_dir / "costs.jsonl",
        db_path=temp_dir / "costs.db",
        enable_sqlite=False,  # JSONL-only mode
    )
    tracker.initialize()

    num_writers = 5
    num_readers = 5
    records_per_writer = 10
    summaries: list[CostSummary] = []
    threads = []

    def write_costs(thread_id: int) -> None:
        """Write costs from a thread."""
        for i in range(records_per_writer):
            record = CostRecord(
                timestamp=datetime.now(timezone.utc).isoformat(),
                model=f"model-{thread_id}",
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
                cost_usd=0.01,
                agent=f"agent-{thread_id}",
            )
            tracker.record_cost(record)

    def read_summaries() -> None:
        """Read summaries from a thread."""
        for _ in range(10):
            summary = tracker.get_summary()
            summaries.append(summary)

    # Start writer threads
    for tid in range(num_writers):
        thread = threading.Thread(target=write_costs, args=(tid,))
        threads.append(thread)
        thread.start()

    # Start reader threads
    for _ in range(num_readers):
        thread = threading.Thread(target=read_summaries)
        threads.append(thread)
        thread.start()

    # Wait for all threads
    for thread in threads:
        thread.join()

    # Final summary should have all records
    final_summary = tracker.get_summary()
    expected_total = num_writers * records_per_writer
    assert final_summary.total_calls == expected_total
    assert final_summary.total_cost_usd == pytest.approx(expected_total * 0.01)

    # All intermediate summaries should be consistent
    # (no partial line reads or corrupted JSON)
    for summary in summaries:
        # Each summary should have valid totals
        assert summary.total_calls >= 0
        assert summary.total_cost_usd >= 0
        # Cost should match call count (each call is 0.01)
        if summary.total_calls > 0:
            assert summary.total_cost_usd == pytest.approx(summary.total_calls * 0.01)

    tracker.close()


def test_get_tracker_uses_runs_costs_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Global tracker should initialize under .runs/costs by default."""
    monkeypatch.chdir(tmp_path)
    import agdd.observability.cost_tracker as ct_module

    # Reset singleton before creating tracker
    monkeypatch.setattr(ct_module, "_tracker", None)

    tracker = get_tracker()
    try:
        assert tracker.jsonl_path == DEFAULT_JSONL_PATH
        assert tracker.db_path == DEFAULT_DB_PATH
        assert (tmp_path / DEFAULT_COSTS_DIR).exists()
        assert (tmp_path / DEFAULT_DB_PATH).exists()
    finally:
        tracker.close()
        monkeypatch.setattr(ct_module, "_tracker", None)
