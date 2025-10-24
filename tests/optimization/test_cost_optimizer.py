"""
Integration tests for cost optimizer.

Tests verify that different SLA parameters result in different execution plans,
demonstrating the centralized decision logic for mode, model tier, cache, and batch.
"""

from pathlib import Path

import pytest

from agdd.optimization.optimizer import (
    CacheStrategy,
    CostOptimizer,
    ExecutionMode,
    ModelTier,
    SLAParameters,
    optimize_for_sla,
)


class TestCostOptimizer:
    """Test suite for CostOptimizer"""

    def test_realtime_high_quality(self) -> None:
        """Test realtime + high quality → REALTIME + PREMIUM"""
        sla = SLAParameters(
            max_latency_ms=2000,
            max_cost_usd=None,
            min_quality=0.95,
            realtime_required=True,
            allow_cache=True,
            allow_batch=False,
        )

        optimizer = CostOptimizer()
        plan = optimizer.optimize(sla)

        assert plan.mode == ExecutionMode.REALTIME
        assert plan.model_tier == ModelTier.PREMIUM
        assert plan.enable_batch is False
        assert "Realtime required" in plan.reasoning
        assert "High quality" in plan.reasoning

    def test_batch_low_cost(self) -> None:
        """Test non-realtime + low cost → BATCH + LOCAL/MINI"""
        sla = SLAParameters(
            max_latency_ms=None,
            max_cost_usd=0.0005,
            min_quality=0.5,
            realtime_required=False,
            allow_cache=True,
            allow_batch=True,
        )

        optimizer = CostOptimizer()
        plan = optimizer.optimize(sla)

        assert plan.mode == ExecutionMode.BATCH
        assert plan.model_tier in (ModelTier.LOCAL, ModelTier.MINI)
        assert plan.enable_batch is True
        assert "BATCH mode" in plan.reasoning
        assert "Low cost budget" in plan.reasoning

    def test_standard_quality_balanced(self) -> None:
        """Test balanced scenario → REALTIME + STANDARD"""
        sla = SLAParameters(
            max_latency_ms=3000,
            max_cost_usd=0.015,
            min_quality=0.75,
            realtime_required=True,
            allow_cache=True,
            allow_batch=False,
        )

        optimizer = CostOptimizer()
        plan = optimizer.optimize(sla)

        assert plan.mode == ExecutionMode.REALTIME
        assert plan.model_tier == ModelTier.STANDARD
        assert plan.cache_strategy in (CacheStrategy.CONSERVATIVE, CacheStrategy.AGGRESSIVE)

    def test_aggressive_caching_for_low_cost(self) -> None:
        """Test aggressive caching is selected for low-cost scenarios"""
        sla = SLAParameters(
            max_cost_usd=0.001,
            min_quality=0.6,
            allow_cache=True,
        )

        optimizer = CostOptimizer()
        plan = optimizer.optimize(sla)

        assert plan.cache_strategy == CacheStrategy.AGGRESSIVE
        assert plan.estimated_cost_usd < 0.001

    def test_no_caching_when_disabled(self) -> None:
        """Test caching is disabled when allow_cache=False"""
        sla = SLAParameters(
            max_cost_usd=0.001,
            allow_cache=False,
        )

        optimizer = CostOptimizer()
        plan = optimizer.optimize(sla)

        assert plan.cache_strategy == CacheStrategy.NONE

    def test_batch_disabled_for_realtime(self) -> None:
        """Test batching is disabled for realtime workloads"""
        sla = SLAParameters(
            realtime_required=True,
            allow_batch=True,
        )

        optimizer = CostOptimizer()
        plan = optimizer.optimize(sla)

        assert plan.mode == ExecutionMode.REALTIME
        assert plan.enable_batch is False

    def test_optimizer_with_policy_file(self) -> None:
        """Test optimizer loads policy file correctly"""
        # Use the auto-optimize.yaml file we created
        policy_path = Path(__file__).parents[2] / "catalog/routing/policies/auto-optimize.yaml"

        optimizer = CostOptimizer(policy_path=policy_path)
        assert optimizer.policy is not None
        assert isinstance(optimizer.policy, dict)

        # Verify optimizer still works with policy loaded
        sla = SLAParameters(min_quality=0.8)
        plan = optimizer.optimize(sla)
        assert plan.model_tier == ModelTier.STANDARD

    def test_convenience_function(self) -> None:
        """Test optimize_for_sla convenience function"""
        sla = SLAParameters(
            max_cost_usd=0.0001,
            min_quality=0.5,
            realtime_required=False,
        )

        plan = optimize_for_sla(sla)

        assert plan.mode == ExecutionMode.BATCH
        assert plan.model_tier == ModelTier.LOCAL


class TestSLAParameterSwitching:
    """
    Integration tests demonstrating SLA parameter switching.

    These tests verify the acceptance criteria: different SLA parameters
    result in different execution plan selections.
    """

    @pytest.mark.parametrize(
        "sla_params,expected_mode,expected_tier",
        [
            # Realtime scenarios
            (
                {"realtime_required": True, "min_quality": 0.95},
                ExecutionMode.REALTIME,
                ModelTier.PREMIUM,
            ),
            (
                {"realtime_required": True, "min_quality": 0.75},
                ExecutionMode.REALTIME,
                ModelTier.STANDARD,
            ),
            (
                {"realtime_required": True, "max_cost_usd": 0.0005},
                ExecutionMode.REALTIME,
                ModelTier.LOCAL,
            ),
            # Batch scenarios
            (
                {"realtime_required": False, "min_quality": 0.6},
                ExecutionMode.BATCH,
                ModelTier.MINI,
            ),
            (
                {"realtime_required": False, "max_cost_usd": 0.0001},
                ExecutionMode.BATCH,
                ModelTier.LOCAL,
            ),
        ],
    )
    def test_sla_switching(
        self,
        sla_params: dict[str, float | bool],
        expected_mode: ExecutionMode,
        expected_tier: ModelTier,
    ) -> None:
        """Test that different SLA parameters produce different plans"""
        sla = SLAParameters(**sla_params)  # type: ignore[arg-type]
        optimizer = CostOptimizer()
        plan = optimizer.optimize(sla)

        assert plan.mode == expected_mode, (
            f"Expected mode {expected_mode}, got {plan.mode} for params {sla_params}"
        )
        assert plan.model_tier == expected_tier, (
            f"Expected tier {expected_tier}, got {plan.model_tier} for params {sla_params}"
        )

    def test_cost_constraint_switches_tier(self) -> None:
        """Test that tightening cost constraint switches to cheaper tier"""
        # Expensive budget → premium tier
        sla_expensive = SLAParameters(max_cost_usd=0.05, min_quality=0.95)
        plan_expensive = optimize_for_sla(sla_expensive)

        # Cheap budget → local/mini tier
        sla_cheap = SLAParameters(max_cost_usd=0.0005, min_quality=0.95)
        plan_cheap = optimize_for_sla(sla_cheap)

        # Despite same quality requirement, cost constraint changes tier
        assert plan_expensive.model_tier == ModelTier.PREMIUM
        assert plan_cheap.model_tier == ModelTier.LOCAL
        assert plan_expensive.estimated_cost_usd > plan_cheap.estimated_cost_usd

    def test_quality_requirement_switches_tier(self) -> None:
        """Test that increasing quality requirement switches to better tier"""
        # Low quality → mini tier
        sla_low_quality = SLAParameters(min_quality=0.5)
        plan_low = optimize_for_sla(sla_low_quality)

        # Medium quality → standard tier
        sla_medium_quality = SLAParameters(min_quality=0.75)
        plan_medium = optimize_for_sla(sla_medium_quality)

        # High quality → premium tier
        sla_high_quality = SLAParameters(min_quality=0.95)
        plan_high = optimize_for_sla(sla_high_quality)

        assert plan_low.model_tier == ModelTier.MINI
        assert plan_medium.model_tier == ModelTier.STANDARD
        assert plan_high.model_tier == ModelTier.PREMIUM

    def test_realtime_flag_switches_mode_and_batch(self) -> None:
        """Test that realtime_required flag controls mode and batching"""
        # Realtime scenario
        sla_realtime = SLAParameters(
            realtime_required=True,
            allow_batch=True,
        )
        plan_realtime = optimize_for_sla(sla_realtime)

        # Batch scenario (same SLA except realtime flag)
        sla_batch = SLAParameters(
            realtime_required=False,
            allow_batch=True,
        )
        plan_batch = optimize_for_sla(sla_batch)

        # Verify mode switches
        assert plan_realtime.mode == ExecutionMode.REALTIME
        assert plan_batch.mode == ExecutionMode.BATCH

        # Verify batch processing only enabled for non-realtime
        assert plan_realtime.enable_batch is False
        assert plan_batch.enable_batch is True

    def test_cache_strategy_switches_based_on_cost(self) -> None:
        """Test that cache strategy adapts to cost constraints"""
        # Very low cost → aggressive caching
        sla_ultra_cheap = SLAParameters(
            max_cost_usd=0.001,
            allow_cache=True,
        )
        plan_ultra_cheap = optimize_for_sla(sla_ultra_cheap)

        # Higher cost → conservative caching
        sla_moderate = SLAParameters(
            max_cost_usd=0.01,
            min_quality=0.8,
            allow_cache=True,
        )
        plan_moderate = optimize_for_sla(sla_moderate)

        # No caching allowed
        sla_no_cache = SLAParameters(
            allow_cache=False,
        )
        plan_no_cache = optimize_for_sla(sla_no_cache)

        assert plan_ultra_cheap.cache_strategy == CacheStrategy.AGGRESSIVE
        assert plan_moderate.cache_strategy == CacheStrategy.CONSERVATIVE
        assert plan_no_cache.cache_strategy == CacheStrategy.NONE
