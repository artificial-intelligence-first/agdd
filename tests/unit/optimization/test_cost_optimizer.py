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
        """Test balanced scenario → REALTIME + MINI (cost-efficient)"""
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
        # MINI (0.8 quality) meets 0.75 requirement and is more cost-efficient
        assert plan.model_tier == ModelTier.MINI
        assert plan.cache_strategy in (CacheStrategy.CONSERVATIVE, CacheStrategy.AGGRESSIVE)

    def test_aggressive_caching_for_low_cost(self) -> None:
        """Test aggressive caching is selected for low-cost scenarios"""
        sla = SLAParameters(
            max_cost_usd=0.003,  # Allows MINI (cost 0.002)
            min_quality=0.6,
            allow_cache=True,
        )

        optimizer = CostOptimizer()
        plan = optimizer.optimize(sla)

        assert plan.cache_strategy == CacheStrategy.AGGRESSIVE
        assert sla.max_cost_usd is not None
        assert plan.estimated_cost_usd <= sla.max_cost_usd

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
        # MINI (0.8) exactly meets requirement and is most cost-efficient
        assert plan.model_tier == ModelTier.MINI

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

    def test_latency_constraint_forces_realtime(self) -> None:
        """Test that tight latency constraint forces REALTIME even when not required"""
        # Batch mode would add ~5000ms overhead, exceeding 1000ms budget
        sla = SLAParameters(
            realtime_required=False,  # BATCH preferred
            max_latency_ms=1000,  # But tight latency constraint
            min_quality=0.7,
        )

        optimizer = CostOptimizer()
        plan = optimizer.optimize(sla)

        # Should select REALTIME to meet latency constraint
        assert plan.mode == ExecutionMode.REALTIME
        assert sla.max_latency_ms is not None
        assert plan.estimated_latency_ms <= sla.max_latency_ms
        assert "Tight latency constraint" in plan.reasoning

    def test_latency_constraint_allows_batch(self) -> None:
        """Test that loose latency constraint allows BATCH"""
        # Batch mode latency (~5000-6000ms) fits within 10000ms budget
        sla = SLAParameters(
            realtime_required=False,
            max_latency_ms=10000,  # Loose constraint
            min_quality=0.7,
        )

        optimizer = CostOptimizer()
        plan = optimizer.optimize(sla)

        # Should select BATCH since it fits latency budget
        assert plan.mode == ExecutionMode.BATCH
        assert sla.max_latency_ms is not None
        assert plan.estimated_latency_ms <= sla.max_latency_ms
        assert "allows BATCH mode" in plan.reasoning

    def test_realtime_required_overrides_latency(self) -> None:
        """Test that realtime_required=True takes precedence"""
        sla = SLAParameters(
            realtime_required=True,
            max_latency_ms=10000,  # Loose enough for BATCH
            min_quality=0.7,
        )

        optimizer = CostOptimizer()
        plan = optimizer.optimize(sla)

        # Should select REALTIME due to explicit requirement
        assert plan.mode == ExecutionMode.REALTIME
        assert "Realtime required" in plan.reasoning


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
                ModelTier.MINI,  # MINI (0.8) meets 0.75 and is cost-efficient
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
                ModelTier.MINI,  # MINI (0.8) meets 0.6
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
        # Expensive budget → premium tier (quality requirement is high)
        sla_expensive = SLAParameters(max_cost_usd=0.05, min_quality=0.95)
        plan_expensive = optimize_for_sla(sla_expensive)

        # Cheap budget → LOCAL (cost ceiling enforced)
        sla_cheap = SLAParameters(max_cost_usd=0.0005, min_quality=0.95)
        plan_cheap = optimize_for_sla(sla_cheap)

        # Expensive budget allows PREMIUM (meets quality + cost)
        assert plan_expensive.model_tier == ModelTier.PREMIUM

        # Cheap budget selects LOCAL (only tier within budget)
        # Cost ceiling is enforced even though quality requirement can't be met
        assert plan_cheap.model_tier == ModelTier.LOCAL

        # With lower quality requirement that LOCAL can meet
        sla_low_quality_cheap = SLAParameters(max_cost_usd=0.0005, min_quality=0.5)
        plan_low_quality_cheap = optimize_for_sla(sla_low_quality_cheap)
        assert plan_low_quality_cheap.model_tier == ModelTier.LOCAL

    def test_quality_requirement_switches_tier(self) -> None:
        """Test that increasing quality requirement switches to better tier"""
        # Low quality → LOCAL tier (0.5 quality)
        sla_low_quality = SLAParameters(min_quality=0.5)
        plan_low = optimize_for_sla(sla_low_quality)

        # Medium quality → MINI tier (0.8 quality)
        sla_medium_quality = SLAParameters(min_quality=0.75)
        plan_medium = optimize_for_sla(sla_medium_quality)

        # High quality → STANDARD tier (0.9 quality)
        sla_high_quality = SLAParameters(min_quality=0.85)
        plan_high = optimize_for_sla(sla_high_quality)

        # Very high quality → PREMIUM tier (0.95 quality)
        sla_very_high_quality = SLAParameters(min_quality=0.95)
        plan_very_high = optimize_for_sla(sla_very_high_quality)

        assert plan_low.model_tier == ModelTier.LOCAL
        assert plan_medium.model_tier == ModelTier.MINI
        assert plan_high.model_tier == ModelTier.STANDARD
        assert plan_very_high.model_tier == ModelTier.PREMIUM

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
            max_cost_usd=0.003,  # Allows MINI
            allow_cache=True,
        )
        plan_ultra_cheap = optimize_for_sla(sla_ultra_cheap)

        # Higher cost with STANDARD tier → conservative caching
        sla_moderate = SLAParameters(
            max_cost_usd=0.015,
            min_quality=0.9,  # Requires STANDARD
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

    def test_cost_ceiling_prevents_expensive_tier(self) -> None:
        """
        Test that cost ceiling prevents selecting expensive tiers.

        Regression test for P1 review comment:
        SLAParameters(max_cost_usd=0.005, min_quality=0.8) should select
        MINI (not STANDARD) because STANDARD base cost is 0.01 > budget.
        """
        sla = SLAParameters(
            max_cost_usd=0.005,
            min_quality=0.8,
        )
        plan = optimize_for_sla(sla)

        # Should select MINI because STANDARD (0.01) exceeds budget
        assert plan.model_tier == ModelTier.MINI
        # Final cost should be within budget even without caching
        assert sla.max_cost_usd is not None
        assert plan.estimated_cost_usd <= sla.max_cost_usd

    def test_cost_ceiling_enforced_when_quality_unattainable(self) -> None:
        """Test that cost ceiling is enforced even when quality can't be met."""
        sla = SLAParameters(
            max_cost_usd=0.0001,  # Only LOCAL is affordable (cost 0.0)
            min_quality=0.9,  # Requires STANDARD+ quality
        )
        plan = optimize_for_sla(sla)

        # Should select LOCAL (best quality within budget)
        # Even though it doesn't meet quality requirement, cost ceiling is respected
        assert plan.model_tier == ModelTier.LOCAL

    def test_cost_ceiling_with_multiple_quality_levels(self) -> None:
        """Test cost ceiling respects budget across different quality levels."""
        test_cases = [
            # (max_cost, min_quality, expected_tier)
            # With tier_quality: LOCAL=0.5, MINI=0.8, STANDARD=0.9, PREMIUM=0.95
            (0.015, 0.6, ModelTier.MINI),  # MINI (0.8) meets 0.6 and fits budget
            (0.005, 0.6, ModelTier.MINI),  # MINI (0.8) meets 0.6 and fits budget
            (0.001, 0.6, ModelTier.LOCAL),  # Only LOCAL fits budget (cost ceiling enforced)
            (0.025, 0.85, ModelTier.STANDARD),  # STANDARD (0.9) meets 0.85, fits budget
            (0.005, 0.85, ModelTier.MINI),  # STANDARD needed, but only MINI fits budget
            (0.015, 0.9, ModelTier.STANDARD),  # STANDARD (0.9) exactly meets 0.9, fits budget
        ]

        for max_cost, min_quality, expected_tier in test_cases:
            sla = SLAParameters(
                max_cost_usd=max_cost,
                min_quality=min_quality,
            )
            plan = optimize_for_sla(sla)
            assert plan.model_tier == expected_tier, (
                f"Failed for max_cost={max_cost}, min_quality={min_quality}: "
                f"expected {expected_tier}, got {plan.model_tier}"
            )
