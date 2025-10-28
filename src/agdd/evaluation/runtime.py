"""
Evaluation Runtime - Executes evaluators and collects metrics

Provides interfaces for running pre_eval and post_eval hooks on agent execution.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, cast

from agdd.registry import EvalDescriptor, MetricConfig, Registry, get_registry

logger = logging.getLogger(__name__)

MetricCallable = Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]


@dataclass
class MetricResult:
    """Result from a single metric evaluation"""

    metric_id: str
    metric_name: str
    score: float  # 0.0 - 1.0
    passed: bool
    threshold: float
    weight: float
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    duration_ms: float = 0.0


@dataclass
class EvalResult:
    """Result from evaluator execution"""

    eval_slug: str
    hook_type: str  # "pre_eval" or "post_eval"
    agent_slug: str
    overall_score: float  # Weighted average of metric scores
    passed: bool  # All critical metrics passed
    fail_open: bool  # If false (fail-closed), failures should block execution
    metrics: List[MetricResult] = field(default_factory=list)
    duration_ms: float = 0.0
    error: Optional[str] = None


class EvalRuntime:
    """Runtime for executing evaluators and collecting metrics"""

    def __init__(self, registry: Optional[Registry] = None):
        self.registry = registry or get_registry()
        self._metric_cache: Dict[str, Dict[str, MetricCallable]] = {}

    def _load_metrics(self, eval_slug: str) -> Dict[str, MetricCallable]:
        """Load metric functions from evaluator's metric module"""
        if eval_slug in self._metric_cache:
            return self._metric_cache[eval_slug]

        # Construct path to metric module
        metric_module_path = (
            self.registry.base_path / "catalog" / "evals" / eval_slug / "metric" / "validator.py"
        )

        if not metric_module_path.exists():
            logger.warning(f"Metric module not found for evaluator '{eval_slug}': {metric_module_path}")
            return {}

        try:
            # Load module with proper package context to support relative imports
            import importlib.util
            import sys

            # Use dotted package path to preserve package context
            module_name = f"catalog.evals.{eval_slug}.metric.validator"

            spec = importlib.util.spec_from_file_location(
                module_name, metric_module_path
            )
            if spec is None or spec.loader is None:
                logger.error(f"Cannot create module spec for {metric_module_path}")
                return {}

            module = importlib.util.module_from_spec(spec)

            # Set __package__ explicitly to enable relative imports
            module.__package__ = f"catalog.evals.{eval_slug}.metric"

            sys.modules[spec.name] = module
            spec.loader.exec_module(module)

            # Extract METRICS dictionary if available
            if hasattr(module, "METRICS") and isinstance(module.METRICS, dict):
                self._metric_cache[eval_slug] = cast(Dict[str, MetricCallable], module.METRICS)
                return self._metric_cache[eval_slug]

            # Fallback: Load individual metric functions by name
            metrics: Dict[str, MetricCallable] = {}
            for attr_name in dir(module):
                if not attr_name.startswith("_"):
                    attr = getattr(module, attr_name)
                    if callable(attr):
                        metrics[attr_name] = cast(MetricCallable, attr)

            self._metric_cache[eval_slug] = metrics
            return metrics

        except Exception as e:
            # Catch import errors, syntax errors, missing dependencies, etc.
            # Log the error but allow evaluation to continue (fail gracefully)
            logger.error(
                f"Failed to load metric module for evaluator '{eval_slug}': {e}",
                exc_info=True
            )
            # Don't cache the error - allow retry on next call
            return {}

    def get_evaluators_for_agent(self, agent_slug: str, hook_type: str) -> List[EvalDescriptor]:
        """
        Get all evaluators that apply to the given agent and hook type.

        Args:
            agent_slug: Agent slug (e.g., "compensation-advisor-sag")
            hook_type: "pre_eval" or "post_eval"

        Returns:
            List of applicable evaluators
        """
        applicable_evals: List[EvalDescriptor] = []

        for eval_slug in self.registry.list_evals():
            try:
                eval_desc = self.registry.load_eval(eval_slug)
                if eval_desc.hook_type == hook_type and agent_slug in eval_desc.target_agents:
                    applicable_evals.append(eval_desc)
            except Exception as e:
                logger.warning(f"Failed to load evaluator '{eval_slug}': {e}")

        return applicable_evals

    def evaluate(
        self, eval_slug: str, payload: Dict[str, Any], context: Dict[str, Any]
    ) -> EvalResult:
        """
        Execute an evaluator on the given payload.

        Args:
            eval_slug: Evaluator slug (e.g., "compensation-validator")
            payload: Data to evaluate (agent input or output)
            context: Execution context (agent_slug, run_id, etc.)

        Returns:
            EvalResult with aggregated scores and details
        """
        t0 = time.time()

        try:
            eval_desc = self.registry.load_eval(eval_slug)
        except Exception as e:
            logger.error(f"Failed to load evaluator '{eval_slug}': {e}")
            return EvalResult(
                eval_slug=eval_slug,
                hook_type="post_eval",
                agent_slug=context.get("agent_slug", "unknown"),
                overall_score=0.0,
                passed=False,
                fail_open=False,  # Treat load failures as fail-closed for safety
                error=f"Failed to load evaluator: {e}",
                duration_ms=(time.time() - t0) * 1000,
            )

        # Load metric functions
        metrics_callable = self._load_metrics(eval_slug)

        # Execute each metric
        metric_results: List[MetricResult] = []
        total_weighted_score = 0.0
        total_weight = 0.0

        for metric_config in eval_desc.metrics:
            metric_t0 = time.time()

            if metric_config.id not in metrics_callable:
                logger.warning(
                    f"Metric '{metric_config.id}' not found in evaluator '{eval_slug}'"
                )
                metric_results.append(
                    MetricResult(
                        metric_id=metric_config.id,
                        metric_name=metric_config.name,
                        score=0.0,
                        passed=False,
                        threshold=metric_config.threshold,
                        weight=metric_config.weight,
                        error=f"Metric function '{metric_config.id}' not found",
                        duration_ms=(time.time() - metric_t0) * 1000,
                    )
                )
                continue

            try:
                # Execute metric function
                metric_fn = metrics_callable[metric_config.id]
                result = metric_fn(payload, context)

                # Validate result format
                if not isinstance(result, dict):
                    raise ValueError(f"Metric '{metric_config.id}' must return dict")

                score = float(result.get("score", 0.0))
                passed = bool(result.get("passed", score >= metric_config.threshold))
                details = result.get("details", {})

                metric_result = MetricResult(
                    metric_id=metric_config.id,
                    metric_name=metric_config.name,
                    score=score,
                    passed=passed,
                    threshold=metric_config.threshold,
                    weight=metric_config.weight,
                    details=details,
                    duration_ms=(time.time() - metric_t0) * 1000,
                )

                metric_results.append(metric_result)

                # Accumulate weighted score
                total_weighted_score += score * metric_config.weight
                total_weight += metric_config.weight

            except Exception as e:
                logger.error(f"Metric '{metric_config.id}' failed: {e}")
                metric_results.append(
                    MetricResult(
                        metric_id=metric_config.id,
                        metric_name=metric_config.name,
                        score=0.0,
                        passed=False,
                        threshold=metric_config.threshold,
                        weight=metric_config.weight,
                        error=str(e),
                        duration_ms=(time.time() - metric_t0) * 1000,
                    )
                )

        # Calculate overall score
        overall_score = total_weighted_score / total_weight if total_weight > 0 else 0.0

        # Determine if evaluation passed
        # All metrics with fail_on_threshold=True must pass
        critical_failures = [
            m
            for m, config in zip(metric_results, eval_desc.metrics)
            if not m.passed and config.fail_on_threshold
        ]
        passed = len(critical_failures) == 0

        # Extract fail_open setting from execution config (default: True = fail-open)
        fail_open = eval_desc.execution.get("fail_open", True)

        return EvalResult(
            eval_slug=eval_slug,
            hook_type=eval_desc.hook_type,
            agent_slug=context.get("agent_slug", "unknown"),
            overall_score=overall_score,
            passed=passed,
            fail_open=fail_open,
            metrics=metric_results,
            duration_ms=(time.time() - t0) * 1000,
        )

    def evaluate_all(
        self, agent_slug: str, hook_type: str, payload: Dict[str, Any], context: Dict[str, Any]
    ) -> List[EvalResult]:
        """
        Execute all applicable evaluators for an agent.

        Args:
            agent_slug: Agent slug
            hook_type: "pre_eval" or "post_eval"
            payload: Data to evaluate
            context: Execution context

        Returns:
            List of EvalResult from all applicable evaluators
        """
        results: List[EvalResult] = []

        # Iterate through all evaluator slugs, including those that might fail to load
        for eval_slug in self.registry.list_evals():
            try:
                # Try to load evaluator descriptor
                eval_desc = self.registry.load_eval(eval_slug)

                # Check if this evaluator applies to the agent and hook type
                if eval_desc.hook_type != hook_type or agent_slug not in eval_desc.target_agents:
                    continue

                # Evaluator is applicable, run evaluation
                result = self.evaluate(
                    eval_slug, payload, {**context, "agent_slug": agent_slug}
                )
                results.append(result)

            except Exception as e:
                # Evaluator failed to load - treat as fail-closed for safety
                logger.error(f"Failed to load evaluator '{eval_slug}': {e}")
                results.append(EvalResult(
                    eval_slug=eval_slug,
                    hook_type=hook_type,
                    agent_slug=agent_slug,
                    overall_score=0.0,
                    passed=False,
                    fail_open=False,  # Treat load failures as fail-closed
                    error=f"Failed to load evaluator: {e}",
                    duration_ms=0.0,
                ))

        return results
