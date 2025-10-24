"""
Cost optimizer for SLA-based routing decisions.

Centralizes the logic for selecting execution plans, caching strategies,
and batching configurations based on Service Level Agreement parameters.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import yaml


class ExecutionMode(str, Enum):
    """Execution mode for agent tasks."""

    REALTIME = "realtime"
    BATCH = "batch"


class ModelTier(str, Enum):
    """Model tier for quality and cost optimization."""

    LOCAL = "local"  # Local models (ollama, etc.)
    MINI = "mini"  # Small models (gpt-4o-mini, etc.)
    STANDARD = "standard"  # Standard models (gpt-4o, claude-3.5-sonnet)
    PREMIUM = "premium"  # Premium models (claude-opus, gpt-4)


class CacheStrategy(str, Enum):
    """Caching strategy for cost optimization."""

    NONE = "none"
    AGGRESSIVE = "aggressive"  # Cache everything possible
    CONSERVATIVE = "conservative"  # Cache only stable data


@dataclass
class SLAParameters:
    """Service Level Agreement parameters for optimization."""

    # Response time in milliseconds (None = no constraint)
    max_latency_ms: Optional[int] = None

    # Budget constraint (cost per request in USD)
    max_cost_usd: Optional[float] = None

    # Quality requirement (0.0 = lowest, 1.0 = highest)
    min_quality: float = 0.7

    # Whether real-time response is required
    realtime_required: bool = True

    # Whether caching is acceptable
    allow_cache: bool = True

    # Whether batching is acceptable
    allow_batch: bool = True


@dataclass
class ExecutionPlan:
    """Optimized execution plan based on SLA parameters."""

    mode: ExecutionMode
    model_tier: ModelTier
    cache_strategy: CacheStrategy
    enable_batch: bool
    estimated_cost_usd: float
    estimated_latency_ms: int
    reasoning: str


class CostOptimizer:
    """
    Optimizer for selecting execution plans based on SLA parameters.

    This class centralizes the decision logic for:
    - Real-time vs Batch execution
    - Model tier selection (Local/Mini vs Claude/OpenAI)
    - Caching strategy
    - Batching configuration
    """

    def __init__(self, policy_path: Optional[Path] = None) -> None:
        """
        Initialize the cost optimizer.

        Args:
            policy_path: Path to auto-optimize.yaml policy file.
                        If None, uses default built-in rules.
        """
        self.policy: dict[str, Any] = {}
        if policy_path and policy_path.exists():
            with open(policy_path, encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
                if isinstance(loaded, dict):
                    self.policy = loaded

    def optimize(self, sla: SLAParameters) -> ExecutionPlan:
        """
        Select the optimal execution plan based on SLA parameters.

        Decision logic:
        1. Execution Mode:
           - If realtime_required=False -> BATCH
           - Else -> REALTIME

        2. Model Tier:
           - If max_cost_usd < 0.001 -> LOCAL/MINI
           - If min_quality >= 0.9 -> PREMIUM
           - If min_quality >= 0.7 -> STANDARD
           - Else -> MINI

        3. Cache Strategy:
           - If allow_cache=True and max_cost_usd is low -> AGGRESSIVE
           - If allow_cache=True -> CONSERVATIVE
           - Else -> NONE

        4. Batching:
           - If allow_batch=True and mode=BATCH -> True
           - Else -> False

        Args:
            sla: SLA parameters for the request

        Returns:
            Optimized execution plan
        """
        # Determine execution mode
        mode = ExecutionMode.BATCH if not sla.realtime_required else ExecutionMode.REALTIME

        # Determine model tier based on cost and quality requirements
        model_tier = self._select_model_tier(sla)

        # Determine cache strategy
        cache_strategy = self._select_cache_strategy(sla, model_tier)

        # Determine batching
        enable_batch = sla.allow_batch and mode == ExecutionMode.BATCH

        # Estimate cost and latency
        estimated_cost_usd = self._estimate_cost(model_tier, cache_strategy)
        estimated_latency_ms = self._estimate_latency(mode, model_tier, enable_batch)

        # Build reasoning
        reasoning = self._build_reasoning(sla, mode, model_tier, cache_strategy, enable_batch)

        return ExecutionPlan(
            mode=mode,
            model_tier=model_tier,
            cache_strategy=cache_strategy,
            enable_batch=enable_batch,
            estimated_cost_usd=estimated_cost_usd,
            estimated_latency_ms=estimated_latency_ms,
            reasoning=reasoning,
        )

    def _select_model_tier(self, sla: SLAParameters) -> ModelTier:
        """
        Select model tier based on cost and quality requirements.

        Selection strategy:
        1. Find tiers within budget (if specified)
        2. Among those, pick the one that best meets quality requirement
        3. If no tier meets both, prioritize based on which constraint is stricter

        Cost is estimated without caching (worst case) to ensure
        the budget is respected even if caching is disabled.
        """
        # Base costs without caching (worst case for budget compliance)
        base_costs = {
            ModelTier.LOCAL: 0.0,
            ModelTier.MINI: 0.002,
            ModelTier.STANDARD: 0.01,
            ModelTier.PREMIUM: 0.03,
        }

        # Tier quality capabilities (estimated)
        # These represent the typical quality level each tier can achieve
        tier_quality = {
            ModelTier.LOCAL: 0.5,
            ModelTier.MINI: 0.8,
            ModelTier.STANDARD: 0.9,
            ModelTier.PREMIUM: 0.95,
        }

        # All tiers in cost priority order
        all_tiers = [
            ModelTier.LOCAL,
            ModelTier.MINI,
            ModelTier.STANDARD,
            ModelTier.PREMIUM,
        ]

        # Filter by budget (if specified)
        if sla.max_cost_usd is not None:
            affordable = [t for t in all_tiers if base_costs[t] <= sla.max_cost_usd]
        else:
            affordable = all_tiers

        # Among affordable tiers, find the cheapest one that meets quality
        for tier in affordable:
            if tier_quality[tier] >= sla.min_quality:
                return tier

        # No affordable tier meets quality - decide which constraint to violate
        if sla.max_cost_usd is not None:
            # Cost constraint is strict - return best quality within budget
            if affordable:
                # Return highest quality tier we can afford (last in affordable list)
                return affordable[-1]

        # Quality constraint is strict - return cheapest tier that meets quality
        for tier in all_tiers:
            if tier_quality[tier] >= sla.min_quality:
                return tier

        # No tier meets quality requirement - return LOCAL (cheapest)
        return ModelTier.LOCAL

    def _select_cache_strategy(self, sla: SLAParameters, model_tier: ModelTier) -> CacheStrategy:
        """Select caching strategy based on SLA and model tier."""
        if not sla.allow_cache:
            return CacheStrategy.NONE

        # Aggressive caching for cost-sensitive scenarios
        if sla.max_cost_usd is not None and sla.max_cost_usd < 0.005:
            return CacheStrategy.AGGRESSIVE

        # Conservative caching for standard/premium models
        if model_tier in (ModelTier.STANDARD, ModelTier.PREMIUM):
            return CacheStrategy.CONSERVATIVE

        return CacheStrategy.AGGRESSIVE

    def _estimate_cost(self, model_tier: ModelTier, cache_strategy: CacheStrategy) -> float:
        """Estimate cost per request in USD."""
        base_costs = {
            ModelTier.LOCAL: 0.0,
            ModelTier.MINI: 0.002,
            ModelTier.STANDARD: 0.01,
            ModelTier.PREMIUM: 0.03,
        }

        base_cost = base_costs[model_tier]

        # Apply cache discount
        if cache_strategy == CacheStrategy.AGGRESSIVE:
            return base_cost * 0.3
        elif cache_strategy == CacheStrategy.CONSERVATIVE:
            return base_cost * 0.6

        return base_cost

    def _estimate_latency(
        self, mode: ExecutionMode, model_tier: ModelTier, enable_batch: bool
    ) -> int:
        """Estimate latency in milliseconds."""
        base_latencies = {
            ModelTier.LOCAL: 500,
            ModelTier.MINI: 1000,
            ModelTier.STANDARD: 2000,
            ModelTier.PREMIUM: 3000,
        }

        latency = base_latencies[model_tier]

        # Batch mode adds overhead
        if enable_batch:
            latency += 5000

        # Realtime mode is optimized
        if mode == ExecutionMode.REALTIME:
            latency = int(latency * 0.8)

        return latency

    def _build_reasoning(
        self,
        sla: SLAParameters,
        mode: ExecutionMode,
        model_tier: ModelTier,
        cache_strategy: CacheStrategy,
        enable_batch: bool,
    ) -> str:
        """Build human-readable reasoning for the decision."""
        parts = []

        # Mode reasoning
        if mode == ExecutionMode.BATCH:
            parts.append("Non-realtime workload → BATCH mode")
        else:
            parts.append("Realtime required → REALTIME mode")

        # Model tier reasoning
        if sla.max_cost_usd and sla.max_cost_usd < 0.001:
            parts.append(f"Low cost budget (${sla.max_cost_usd}) → {model_tier.value.upper()}")
        elif sla.min_quality >= 0.9:
            parts.append(
                f"High quality requirement ({sla.min_quality}) → {model_tier.value.upper()}"
            )
        else:
            parts.append(f"Quality requirement ({sla.min_quality}) → {model_tier.value.upper()}")

        # Cache reasoning
        if cache_strategy != CacheStrategy.NONE:
            parts.append(f"Caching enabled → {cache_strategy.value.upper()}")

        # Batch reasoning
        if enable_batch:
            parts.append("Batch processing enabled for cost optimization")

        return "; ".join(parts)


def optimize_for_sla(sla: SLAParameters, policy_path: Optional[Path] = None) -> ExecutionPlan:
    """
    Convenience function to optimize execution plan for given SLA.

    Args:
        sla: SLA parameters
        policy_path: Optional path to policy file

    Returns:
        Optimized execution plan
    """
    optimizer = CostOptimizer(policy_path=policy_path)
    return optimizer.optimize(sla)
