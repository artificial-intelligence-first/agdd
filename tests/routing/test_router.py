"""Tests for routing.router module."""

from pathlib import Path

import pytest

from agdd.routing.policy import Route, RoutingPolicy
from agdd.routing.router import Plan, get_plan, load_policy


@pytest.fixture
def base_path() -> Path:
    """Get project root path."""
    # tests/routing/ -> tests/ -> root
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def sample_policy() -> RoutingPolicy:
    """Create sample routing policy for testing."""
    routes = [
        Route(
            task_type="offer-orchestration",
            provider="anthropic",
            model="claude-3-5-sonnet-20241022",
            use_batch=False,
            use_cache=True,
            structured_output=True,
            moderation=False,
            priority=100,
            metadata={"max_tokens": 4096},
        ),
        Route(
            task_type="offer.*",
            provider="anthropic",
            model="claude-3-5-sonnet-20241022",
            use_batch=False,
            use_cache=True,
            structured_output=True,
            moderation=False,
            priority=90,
            metadata={"max_tokens": 4096},
        ),
        Route(
            task_type="*",
            provider="anthropic",
            model="claude-3-5-sonnet-20241022",
            use_batch=False,
            use_cache=False,
            structured_output=False,
            moderation=False,
            priority=0,
            metadata={"max_tokens": 2048},
        ),
    ]
    return RoutingPolicy(name="test", description="Test policy", routes=routes)


def test_plan_from_route() -> None:
    """Test Plan creation from Route."""
    route = Route(
        task_type="test-task",
        provider="anthropic",
        model="claude-3-5-sonnet-20241022",
        use_batch=True,
        use_cache=True,
        structured_output=True,
        moderation=False,
        priority=100,
        metadata={"key": "value"},
    )

    plan = Plan.from_route(route)

    assert plan.task_type == "test-task"
    assert plan.provider == "anthropic"
    assert plan.model == "claude-3-5-sonnet-20241022"
    assert plan.use_batch is True
    assert plan.use_cache is True
    assert plan.structured_output is True
    assert plan.moderation is False
    assert plan.metadata == {"key": "value"}


def test_get_plan_exact_match(sample_policy: RoutingPolicy) -> None:
    """Test get_plan with exact task type match."""
    plan = get_plan("offer-orchestration", policy=sample_policy)

    assert plan is not None
    assert plan.task_type == "offer-orchestration"
    assert plan.provider == "anthropic"
    assert plan.model == "claude-3-5-sonnet-20241022"
    assert plan.use_batch is False
    assert plan.use_cache is True
    assert plan.structured_output is True
    assert plan.moderation is False


def test_get_plan_pattern_match(sample_policy: RoutingPolicy) -> None:
    """Test get_plan with pattern matching."""
    plan = get_plan("offer.generate", policy=sample_policy)

    assert plan is not None
    assert plan.task_type == "offer.*"
    assert plan.provider == "anthropic"
    assert plan.use_cache is True
    assert plan.structured_output is True


def test_get_plan_wildcard_match(sample_policy: RoutingPolicy) -> None:
    """Test get_plan with wildcard match."""
    plan = get_plan("unknown-task", policy=sample_policy)

    assert plan is not None
    assert plan.task_type == "*"
    assert plan.provider == "anthropic"
    assert plan.use_batch is False
    assert plan.use_cache is False
    assert plan.structured_output is False


def test_get_plan_with_overrides(sample_policy: RoutingPolicy) -> None:
    """Test get_plan with overrides."""
    plan = get_plan(
        "offer-orchestration",
        overrides={"use_batch": True, "moderation": True},
        policy=sample_policy,
    )

    assert plan is not None
    assert plan.use_batch is True
    assert plan.moderation is True
    assert plan.use_cache is True  # Original value preserved


def test_get_plan_no_match() -> None:
    """Test get_plan when no route matches."""
    empty_policy = RoutingPolicy(name="empty", description="Empty", routes=[])
    plan = get_plan("any-task", policy=empty_policy)

    assert plan is None


def test_load_policy_default(base_path: Path) -> None:
    """Test loading default policy from YAML."""
    policy = load_policy("default", base_path=base_path)

    assert policy.name == "default"
    assert len(policy.routes) > 0

    # Check that routes are sorted by priority
    priorities = [route.priority for route in policy.routes]
    assert priorities == sorted(priorities, reverse=True)


def test_load_policy_cost_optimized(base_path: Path) -> None:
    """Test loading cost-optimized policy."""
    policy = load_policy("cost-optimized", base_path=base_path)

    assert policy.name == "cost-optimized"
    assert len(policy.routes) > 0

    # Cost-optimized should use batch for most routes
    batch_routes = [r for r in policy.routes if r.use_batch]
    assert len(batch_routes) > 0


def test_load_policy_auto_optimize(base_path: Path) -> None:
    """Test loading auto-optimize policy."""
    policy = load_policy("auto-optimize", base_path=base_path)

    assert policy.name == "auto-optimize"
    assert len(policy.routes) > 0


def test_get_plan_default_policy(base_path: Path) -> None:
    """Test get_plan with default policy."""
    # This will use the default policy from catalog/routing/default.yaml
    from agdd.routing import router

    # Reset default policy to force reload
    router._default_policy = None

    plan = get_plan("offer-orchestration")

    assert plan is not None
    assert plan.provider == "anthropic"
    assert plan.task_type == "offer-orchestration"


def test_get_plan_for_various_task_types(sample_policy: RoutingPolicy) -> None:
    """Test get_plan for different task types."""
    test_cases = [
        ("offer-orchestration", True, True, True),
        ("offer.generate", True, True, True),
        ("offer.review", True, True, True),  # Should match offer.*
        ("unknown-task", False, False, False),  # Should match *
    ]

    for task_type, expected_cache, expected_structured, expected_batch in test_cases:
        plan = get_plan(task_type, policy=sample_policy)
        assert plan is not None

        if task_type == "offer-orchestration":
            assert plan.use_cache is expected_cache
            assert plan.structured_output is expected_structured
        elif task_type.startswith("offer."):
            assert plan.use_cache is expected_cache
            assert plan.structured_output is expected_structured
        else:
            assert plan.use_cache is expected_cache
            assert plan.structured_output is expected_structured
