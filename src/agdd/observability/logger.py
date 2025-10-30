"""Lightweight run logger with cost tracking and optional OTel support."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from agdd.observability.cost_tracker import record_llm_cost
from agdd.observability.tracing import initialize_observability
from agdd.routing.router import Plan as LLMPlan


class ObservabilityLogger:
    """Simple logger for agent execution traces with OTel and cost tracking support."""

    def __init__(
        self,
        run_id: str,
        slug: Optional[str] = None,
        base_dir: Optional[Path] = None,
        span_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
        *,
        agent_plan: Optional[dict[str, Any]] = None,
        llm_plan: Optional[LLMPlan] = None,
        enable_otel: bool = False,
    ):
        self.run_id = run_id
        self.slug = slug
        self.base_dir = base_dir or Path.cwd() / ".runs" / "agents"
        self.run_dir = self.base_dir / run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.logs: list[dict[str, Any]] = []
        self.metrics: dict[str, list[dict[str, Any]]] = {}
        self.span_id = span_id or f"span-{uuid.uuid4().hex[:16]}"
        self.parent_span_id = parent_span_id
        self.cost_usd: float = 0.0
        self.token_count: int = 0
        self._cost_entries: int = 0
        self._agent_plan_snapshot = copy.deepcopy(agent_plan) if agent_plan else None
        self._llm_plan_snapshot = self._serialize_llm_plan(llm_plan)
        self.enable_otel = enable_otel

        if enable_otel:
            try:
                initialize_observability()
            except Exception as exc:  # noqa: BLE001
                import logging

                logging.getLogger(__name__).warning(
                    "Failed to initialize observability tracing: %s", exc
                )

    @staticmethod
    def _serialize_llm_plan(plan: Optional[LLMPlan]) -> Optional[dict[str, Any]]:
        if plan is None:
            return None
        return {
            "task_type": plan.task_type,
            "provider": plan.provider,
            "model": plan.model,
            "use_batch": plan.use_batch,
            "use_cache": plan.use_cache,
            "structured_output": plan.structured_output,
            "moderation": plan.moderation,
            "metadata": copy.deepcopy(plan.metadata),
        }

    @property
    def llm_plan_snapshot(self) -> Optional[dict[str, Any]]:
        return copy.deepcopy(self._llm_plan_snapshot) if self._llm_plan_snapshot else None

    @property
    def agent_plan_snapshot(self) -> Optional[dict[str, Any]]:
        return copy.deepcopy(self._agent_plan_snapshot) if self._agent_plan_snapshot else None

    def _atomic_write(self, path: Path, payload: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", delete=False, dir=path.parent, encoding="utf-8"
        ) as tmp:
            tmp.write(payload)
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, path)

    def _write_json(self, path: Path, content: Any) -> None:
        payload = json.dumps(content, ensure_ascii=False, indent=2)
        self._atomic_write(path, payload + "\n")

    def log(self, event: str, data: Dict[str, Any]) -> None:
        """Log an event with OTel span context."""
        entry = {
            "run_id": self.run_id,
            "event": event,
            "timestamp": time.time(),
            "data": data,
            "span_id": self.span_id,
        }
        if self.parent_span_id:
            entry["parent_span_id"] = self.parent_span_id
        self.logs.append(entry)
        log_file = self.run_dir / "logs.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def metric(self, key: str, value: Any) -> None:
        """Record a metric value."""
        if key not in self.metrics:
            self.metrics[key] = []
        self.metrics[key].append({"run_id": self.run_id, "value": value, "timestamp": time.time()})
        metrics_file = self.run_dir / "metrics.json"
        self._write_json(metrics_file, self.metrics)

    def record_cost(
        self,
        cost_usd: float,
        tokens: int = 0,
        *,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        step: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record execution cost and token usage."""
        self.cost_usd += cost_usd
        self.token_count += tokens
        self.metric("cost_usd", cost_usd)
        self.metric("tokens", tokens)
        self._cost_entries += 1

        plan_snapshot = self.llm_plan_snapshot
        model_name = model or (plan_snapshot["model"] if plan_snapshot else "unknown")
        provider_name = provider or (plan_snapshot["provider"] if plan_snapshot else None)

        tracker_metadata: Dict[str, Any] = {
            "provider": provider_name,
            "agent_plan": self.agent_plan_snapshot,
            "llm_plan": plan_snapshot,
        }
        if metadata:
            tracker_metadata.update(metadata)

        placeholder = (
            cost_usd == 0.0
            and int(input_tokens if input_tokens is not None else tokens) == 0
            and int(output_tokens or 0) == 0
        )
        if placeholder:
            tracker_metadata.setdefault("placeholder", True)

        record_llm_cost(
            model=model_name,
            input_tokens=int(input_tokens if input_tokens is not None else tokens),
            output_tokens=int(output_tokens if output_tokens is not None else 0),
            cost_usd=cost_usd,
            run_id=self.run_id,
            step=step,
            agent=self.slug,
            metadata={k: v for k, v in tracker_metadata.items() if v is not None},
        )

    def finalize(self) -> None:
        """Write final summary with cost totals."""
        if self._cost_entries == 0:
            self.record_cost(0.0, 0, step="finalize", metadata={"auto_recorded": True})

        summary_file = self.run_dir / "summary.json"
        summary = {
            "run_id": self.run_id,
            "total_logs": len(self.logs),
            "metrics": self.metrics,
            "run_dir": str(self.run_dir),
            "span_id": self.span_id,
            "cost_usd": self.cost_usd,
            "token_count": self.token_count,
            "otel_enabled": self.enable_otel,
        }
        if self.slug:
            summary["slug"] = self.slug
        if self.parent_span_id:
            summary["parent_span_id"] = self.parent_span_id
        if self._agent_plan_snapshot:
            summary["agent_plan"] = self._agent_plan_snapshot
        if self._llm_plan_snapshot:
            summary["llm_plan"] = self._llm_plan_snapshot
        self._write_json(summary_file, summary)

    def write_plan(self, plan: dict) -> None:
        """Write plan.json to run directory."""
        if not self.run_dir:
            return
        plan_path = self.run_dir / "plan.json"
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2)

    def log_event_envelope(self, event: dict) -> None:
        """Log event in EventEnvelope v1 format."""
        envelope = {
            "ts": datetime.utcnow().isoformat(),
            "run_id": self.run_id,
            "span_id": self.span_id,
            "type": event.get("type", "unknown"),
            "payload": event.get("payload", {}),
            "level": event.get("level", "INFO"),
            "kv": event.get("kv", {}),
        }
        self._write_event(envelope)

    def _write_event(self, envelope: dict) -> None:
        """Write event envelope to events.jsonl."""
        events_file = self.run_dir / "events.jsonl"
        with open(events_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(envelope, ensure_ascii=False) + "\n")

    def snapshot_env_hash(self) -> str:
        """Create hash of current environment for determinism tracking."""
        import os

        env_subset = {
            k: v
            for k, v in os.environ.items()
            if k.startswith(("AGDD_", "OPENAI_", "ANTHROPIC_"))
        }
        env_json = json.dumps(env_subset, sort_keys=True)
        return hashlib.sha256(env_json.encode()).hexdigest()


__all__ = ["ObservabilityLogger"]
