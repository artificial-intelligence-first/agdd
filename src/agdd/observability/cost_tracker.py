"""
Cost tracking with JSONL and SQLite backend support.

This module provides cost tracking for LLM API calls with dual persistence:
- JSONL files for append-only logging and backup
- SQLite (WAL mode) for efficient aggregation and querying

Thread-safe for concurrent access.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_RUNS_DIR = Path(".runs")
DEFAULT_COSTS_DIR = DEFAULT_RUNS_DIR / "costs"
DEFAULT_JSONL_PATH = DEFAULT_COSTS_DIR / "costs.jsonl"
DEFAULT_DB_PATH = DEFAULT_RUNS_DIR / "costs.db"


@dataclass(slots=True)
class CostRecord:
    """Individual cost record for an LLM API call."""

    timestamp: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    run_id: Optional[str] = None
    step: Optional[str] = None
    agent: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": self.cost_usd,
            "run_id": self.run_id,
            "step": self.step,
            "agent": self.agent,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CostRecord:
        """Create from dictionary."""
        return cls(
            timestamp=data["timestamp"],
            model=data["model"],
            input_tokens=data["input_tokens"],
            output_tokens=data["output_tokens"],
            total_tokens=data["total_tokens"],
            cost_usd=data["cost_usd"],
            run_id=data.get("run_id"),
            step=data.get("step"),
            agent=data.get("agent"),
            metadata=data.get("metadata", {}),
        )


@dataclass(slots=True)
class CostSummary:
    """Aggregated cost summary."""

    total_cost_usd: float
    total_tokens: int
    total_input_tokens: int
    total_output_tokens: int
    total_calls: int
    by_model: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    by_agent: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    period_start: Optional[str] = None
    period_end: Optional[str] = None


class CostTracker:
    """
    Thread-safe cost tracker with JSONL and SQLite backends.

    Features:
    - Append-only JSONL logging for audit trail
    - SQLite (WAL mode) for efficient aggregation
    - Thread-safe concurrent writes
    - Flexible querying and aggregation
    """

    def __init__(
        self,
        jsonl_path: str | Path = DEFAULT_JSONL_PATH,
        db_path: str | Path = DEFAULT_DB_PATH,
        enable_sqlite: bool = True,
    ):
        """
        Initialize cost tracker.

        Args:
            jsonl_path: Path to JSONL file for append-only logging
            db_path: Path to SQLite database for aggregation
            enable_sqlite: Enable SQLite backend (default: True)
        """
        self.jsonl_path = Path(jsonl_path)
        self.db_path = Path(db_path)
        self.enable_sqlite = enable_sqlite
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._initialized = False

    def initialize(self) -> None:
        """Initialize storage backends."""
        with self._lock:
            if self._initialized:
                return

            # Create parent directories
            self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)

            if self.enable_sqlite:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                self._conn = sqlite3.connect(
                    self.db_path,
                    check_same_thread=False,
                    isolation_level=None,  # Autocommit mode
                )
                self._conn.row_factory = sqlite3.Row
                self._conn.execute("PRAGMA journal_mode = WAL")
                self._conn.execute("PRAGMA foreign_keys = ON")
                self._create_schema()

            self._initialized = True

    def _create_schema(self) -> None:
        """Create SQLite database schema."""
        conn = self._conn
        if conn is None:
            raise RuntimeError("SQLite connection has not been initialized")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cost_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                model TEXT NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                total_tokens INTEGER NOT NULL,
                cost_usd REAL NOT NULL,
                run_id TEXT,
                step TEXT,
                agent TEXT,
                metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Indexes for efficient querying
        conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON cost_records(timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_model ON cost_records(model)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_agent ON cost_records(agent)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_run_id ON cost_records(run_id)")

    def record_cost(self, record: CostRecord) -> None:
        """
        Record a cost entry to both JSONL and SQLite.

        Args:
            record: Cost record to persist

        Thread-safe for concurrent calls.
        """
        if not self._initialized:
            self.initialize()

        with self._lock:
            # Write to JSONL
            with self.jsonl_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

            # Write to SQLite
            if self.enable_sqlite and self._conn is not None:
                self._conn.execute(
                    """
                    INSERT INTO cost_records
                    (timestamp, model, input_tokens, output_tokens, total_tokens,
                     cost_usd, run_id, step, agent, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.timestamp,
                        record.model,
                        record.input_tokens,
                        record.output_tokens,
                        record.total_tokens,
                        record.cost_usd,
                        record.run_id,
                        record.step,
                        record.agent,
                        json.dumps(record.metadata) if record.metadata else None,
                    ),
                )

    def get_summary(
        self,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        agent: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> CostSummary:
        """
        Get aggregated cost summary.

        Args:
            start_time: ISO 8601 timestamp for period start (inclusive)
            end_time: ISO 8601 timestamp for period end (inclusive)
            agent: Filter by agent name
            run_id: Filter by run ID

        Returns:
            Aggregated cost summary
        """
        if not self._initialized:
            self.initialize()

        if not self.enable_sqlite or self._conn is None:
            # JSONL fallback also needs lock protection for thread safety
            with self._lock:
                return self._get_summary_from_jsonl(start_time, end_time, agent, run_id)

        with self._lock:
            # Build WHERE clause
            conditions = []
            params: List[Any] = []

            if start_time:
                conditions.append("timestamp >= ?")
                params.append(start_time)
            if end_time:
                conditions.append("timestamp <= ?")
                params.append(end_time)
            if agent:
                conditions.append("agent = ?")
                params.append(agent)
            if run_id:
                conditions.append("run_id = ?")
                params.append(run_id)

            conn = self._conn
            if conn is None:
                raise RuntimeError("SQLite connection has not been initialized")

            where_clause = " AND ".join(conditions)
            summary_query = [
                "SELECT",
                "    COALESCE(SUM(cost_usd), 0) as total_cost,",
                "    COALESCE(SUM(total_tokens), 0) as total_tokens,",
                "    COALESCE(SUM(input_tokens), 0) as total_input,",
                "    COALESCE(SUM(output_tokens), 0) as total_output,",
                "    COUNT(*) as total_calls",
                "FROM cost_records",
            ]
            if where_clause:
                summary_query.append("WHERE " + where_clause)
            summary_sql = "\n".join(summary_query)

            row = conn.execute(summary_sql, params).fetchone()

            summary = CostSummary(
                total_cost_usd=float(row["total_cost"]),
                total_tokens=int(row["total_tokens"]),
                total_input_tokens=int(row["total_input"]),
                total_output_tokens=int(row["total_output"]),
                total_calls=int(row["total_calls"]),
                period_start=start_time,
                period_end=end_time,
            )

            # By model
            model_query = [
                "SELECT",
                "    model,",
                "    SUM(cost_usd) as cost,",
                "    SUM(total_tokens) as tokens,",
                "    SUM(input_tokens) as input_tokens,",
                "    SUM(output_tokens) as output_tokens,",
                "    COUNT(*) as calls",
                "FROM cost_records",
            ]
            if where_clause:
                model_query.append("WHERE " + where_clause)
            model_query.extend(
                [
                    "GROUP BY model",
                    "ORDER BY cost DESC",
                ]
            )
            model_sql = "\n".join(model_query)

            rows = conn.execute(model_sql, params).fetchall()

            for row in rows:
                summary.by_model[row["model"]] = {
                    "cost_usd": float(row["cost"]),
                    "tokens": int(row["tokens"]),
                    "input_tokens": int(row["input_tokens"]),
                    "output_tokens": int(row["output_tokens"]),
                    "calls": int(row["calls"]),
                }

            # By agent
            agent_query = [
                "SELECT",
                "    agent,",
                "    SUM(cost_usd) as cost,",
                "    SUM(total_tokens) as tokens,",
                "    SUM(input_tokens) as input_tokens,",
                "    SUM(output_tokens) as output_tokens,",
                "    COUNT(*) as calls",
                "FROM cost_records",
            ]
            if where_clause:
                agent_query.append("WHERE " + where_clause)
            agent_query.extend(
                [
                    "GROUP BY agent",
                    "ORDER BY cost DESC",
                ]
            )
            agent_sql = "\n".join(agent_query)

            rows = conn.execute(agent_sql, params).fetchall()

            for row in rows:
                if row["agent"]:  # Skip NULL agents
                    summary.by_agent[row["agent"]] = {
                        "cost_usd": float(row["cost"]),
                        "tokens": int(row["tokens"]),
                        "input_tokens": int(row["input_tokens"]),
                        "output_tokens": int(row["output_tokens"]),
                        "calls": int(row["calls"]),
                    }

            return summary

    def _get_summary_from_jsonl(
        self,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        agent: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> CostSummary:
        """Fallback: aggregate from JSONL when SQLite is disabled."""
        summary = CostSummary(
            total_cost_usd=0.0,
            total_tokens=0,
            total_input_tokens=0,
            total_output_tokens=0,
            total_calls=0,
            period_start=start_time,
            period_end=end_time,
        )

        if not self.jsonl_path.exists():
            return summary

        with self.jsonl_path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    record = CostRecord.from_dict(data)

                    # Apply filters
                    if start_time and record.timestamp < start_time:
                        continue
                    if end_time and record.timestamp > end_time:
                        continue
                    if agent and record.agent != agent:
                        continue
                    if run_id and record.run_id != run_id:
                        continue

                    # Aggregate
                    summary.total_cost_usd += record.cost_usd
                    summary.total_tokens += record.total_tokens
                    summary.total_input_tokens += record.input_tokens
                    summary.total_output_tokens += record.output_tokens
                    summary.total_calls += 1

                    # By model
                    if record.model not in summary.by_model:
                        summary.by_model[record.model] = {
                            "cost_usd": 0.0,
                            "tokens": 0,
                            "input_tokens": 0,
                            "output_tokens": 0,
                            "calls": 0,
                        }
                    summary.by_model[record.model]["cost_usd"] += record.cost_usd
                    summary.by_model[record.model]["tokens"] += record.total_tokens
                    summary.by_model[record.model]["input_tokens"] += record.input_tokens
                    summary.by_model[record.model]["output_tokens"] += record.output_tokens
                    summary.by_model[record.model]["calls"] += 1

                    # By agent
                    if record.agent:
                        if record.agent not in summary.by_agent:
                            summary.by_agent[record.agent] = {
                                "cost_usd": 0.0,
                                "tokens": 0,
                                "input_tokens": 0,
                                "output_tokens": 0,
                                "calls": 0,
                            }
                        summary.by_agent[record.agent]["cost_usd"] += record.cost_usd
                        summary.by_agent[record.agent]["tokens"] += record.total_tokens
                        summary.by_agent[record.agent]["input_tokens"] += record.input_tokens
                        summary.by_agent[record.agent]["output_tokens"] += record.output_tokens
                        summary.by_agent[record.agent]["calls"] += 1

                except (json.JSONDecodeError, KeyError):
                    continue

        return summary

    def close(self) -> None:
        """Close database connection."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
            self._initialized = False


# Global singleton instance
_tracker: Optional[CostTracker] = None
_tracker_lock = threading.Lock()


def get_tracker() -> CostTracker:
    """Get or create global cost tracker instance."""
    global _tracker
    if _tracker is None:
        with _tracker_lock:
            if _tracker is None:
                _tracker = CostTracker()
                _tracker.initialize()
    return _tracker


def record_llm_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    run_id: Optional[str] = None,
    step: Optional[str] = None,
    agent: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Convenience function to record LLM cost.

    Args:
        model: Model identifier (e.g., "gpt-4", "claude-3-opus")
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        cost_usd: Cost in USD
        run_id: Associated run ID
        step: Step name
        agent: Agent name
        metadata: Additional metadata
    """
    tracker = get_tracker()
    record = CostRecord(
        timestamp=datetime.now(timezone.utc).isoformat(),
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        cost_usd=cost_usd,
        run_id=run_id,
        step=step,
        agent=agent,
        metadata=metadata or {},
    )
    tracker.record_cost(record)
