"""Tests for routing.policy module."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from magsag.routing.policy import Route, RoutingPolicy


@pytest.fixture
def temp_policy_yaml(tmp_path: Path) -> Path:
    """Create temporary policy YAML for testing."""
    policy_data = {
        "name": "test-policy",
        "description": "Test routing policy",
        "routes": [
            {
                "task_type": "task-a",
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "use_batch": True,
                "use_cache": True,
                "structured_output": True,
                "moderation": False,
                "priority": 100,
                "metadata": {"max_tokens": 4096},
            },
            {
                "task_type": "task-b",
                "provider": "openai",
                "model": "gpt-4",
                "use_batch": False,
                "use_cache": True,
                "structured_output": False,
                "moderation": True,
                "priority": 50,
                "metadata": {"temperature": 0.7},
            },
            {
                "task_type": "*",
                "provider": "anthropic",
                "model": "claude-3-5-haiku-20241022",
                "use_batch": True,
                "use_cache": False,
                "structured_output": False,
                "moderation": False,
                "priority": 0,
                "metadata": {},
            },
        ],
    }

    yaml_path = tmp_path / "test-policy.yaml"
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(policy_data, f)

    return yaml_path


def test_route_creation() -> None:
    """Test Route dataclass creation."""
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

    assert route.task_type == "test-task"
    assert route.provider == "anthropic"
    assert route.model == "claude-3-5-sonnet-20241022"
    assert route.use_batch is True
    assert route.use_cache is True
    assert route.structured_output is True
    assert route.moderation is False
    assert route.priority == 100
    assert route.metadata == {"key": "value"}


def test_route_defaults() -> None:
    """Test Route with default values."""
    route = Route(
        task_type="test-task",
        provider="anthropic",
        model="claude-3-5-sonnet-20241022",
    )

    assert route.use_batch is False
    assert route.use_cache is False
    assert route.structured_output is False
    assert route.moderation is False
    assert route.priority == 0
    assert route.metadata == {}


def test_route_immutable() -> None:
    """Test that Route is immutable (frozen)."""
    route = Route(
        task_type="test-task",
        provider="anthropic",
        model="claude-3-5-sonnet-20241022",
    )

    with pytest.raises(Exception):  # FrozenInstanceError in Python 3.11+
        route.use_batch = True  # type: ignore[misc]


def test_routing_policy_from_yaml(temp_policy_yaml: Path) -> None:
    """Test loading RoutingPolicy from YAML."""
    policy = RoutingPolicy.from_yaml(temp_policy_yaml)

    assert policy.name == "test-policy"
    assert policy.description == "Test routing policy"
    assert len(policy.routes) == 3

    # Check routes are sorted by priority (descending)
    assert policy.routes[0].priority == 100
    assert policy.routes[1].priority == 50
    assert policy.routes[2].priority == 0


def test_routing_policy_from_yaml_file_not_found() -> None:
    """Test error when YAML file not found."""
    with pytest.raises(FileNotFoundError):
        RoutingPolicy.from_yaml(Path("/nonexistent/policy.yaml"))


def test_routing_policy_from_yaml_invalid_structure(tmp_path: Path) -> None:
    """Test error when YAML structure is invalid."""
    invalid_yaml = tmp_path / "invalid.yaml"
    with open(invalid_yaml, "w", encoding="utf-8") as f:
        f.write("- this is a list\n")

    with pytest.raises(ValueError, match="must be a mapping"):
        RoutingPolicy.from_yaml(invalid_yaml)


def test_routing_policy_get_route_exact_match(temp_policy_yaml: Path) -> None:
    """Test get_route with exact match."""
    policy = RoutingPolicy.from_yaml(temp_policy_yaml)
    route = policy.get_route("task-a")

    assert route is not None
    assert route.task_type == "task-a"
    assert route.provider == "anthropic"
    assert route.use_batch is True
    assert route.use_cache is True


def test_routing_policy_get_route_wildcard(temp_policy_yaml: Path) -> None:
    """Test get_route with wildcard match."""
    policy = RoutingPolicy.from_yaml(temp_policy_yaml)
    route = policy.get_route("unknown-task")

    assert route is not None
    assert route.task_type == "*"
    assert route.provider == "anthropic"
    assert route.model == "claude-3-5-haiku-20241022"


def test_routing_policy_get_route_no_match() -> None:
    """Test get_route when no route matches."""
    policy = RoutingPolicy(name="empty", description="Empty", routes=[])
    route = policy.get_route("any-task")

    assert route is None


def test_routing_policy_get_route_with_overrides(temp_policy_yaml: Path) -> None:
    """Test get_route with overrides."""
    policy = RoutingPolicy.from_yaml(temp_policy_yaml)
    route = policy.get_route(
        "task-a",
        overrides={"use_batch": False, "moderation": True, "model": "claude-3-opus-20240229"},
    )

    assert route is not None
    assert route.task_type == "task-a"
    assert route.use_batch is False  # Overridden
    assert route.moderation is True  # Overridden
    assert route.model == "claude-3-opus-20240229"  # Overridden
    assert route.use_cache is True  # Original value


def test_routing_policy_get_route_pattern_match(tmp_path: Path) -> None:
    """Test get_route with pattern matching."""
    policy_data = {
        "name": "pattern-test",
        "description": "Test pattern matching",
        "routes": [
            {
                "task_type": "offer.*",
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "priority": 100,
            },
            {
                "task_type": "*",
                "provider": "anthropic",
                "model": "claude-3-5-haiku-20241022",
                "priority": 0,
            },
        ],
    }

    yaml_path = tmp_path / "pattern.yaml"
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(policy_data, f)

    policy = RoutingPolicy.from_yaml(yaml_path)

    # Should match offer.*
    route = policy.get_route("offer.generate")
    assert route is not None
    assert route.task_type == "offer.*"

    # Should match offer.*
    route = policy.get_route("offer.review")
    assert route is not None
    assert route.task_type == "offer.*"

    # Should match *
    route = policy.get_route("other-task")
    assert route is not None
    assert route.task_type == "*"


def test_routing_policy_priority_ordering(tmp_path: Path) -> None:
    """Test that routes are sorted by priority."""
    policy_data: dict[str, Any] = {
        "name": "priority-test",
        "description": "Test priority ordering",
        "routes": [
            {"task_type": "low", "provider": "p1", "model": "m1", "priority": 10},
            {"task_type": "high", "provider": "p2", "model": "m2", "priority": 100},
            {"task_type": "mid", "provider": "p3", "model": "m3", "priority": 50},
        ],
    }

    yaml_path = tmp_path / "priority.yaml"
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(policy_data, f)

    policy = RoutingPolicy.from_yaml(yaml_path)

    # Routes should be sorted by priority (descending)
    assert policy.routes[0].task_type == "high"
    assert policy.routes[1].task_type == "mid"
    assert policy.routes[2].task_type == "low"
