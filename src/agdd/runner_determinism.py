"""
Determinism and Replay functionality for agent execution.

Provides surface API for enabling deterministic mode and capturing/replaying
environment state for reproducible agent runs.
"""

from __future__ import annotations

import copy
import hashlib
import os
import random
import time
from typing import Any, Optional

# Global state for deterministic mode
_deterministic_mode: bool = False
_deterministic_seed: Optional[int] = None


def set_deterministic_mode(enabled: bool) -> None:
    """
    Enable or disable deterministic execution mode.

    When enabled, agent runs will use fixed seeds and settings to ensure
    reproducible results across multiple executions.

    Args:
        enabled: True to enable deterministic mode, False to disable
    """
    global _deterministic_mode
    _deterministic_mode = enabled


def get_deterministic_mode() -> bool:
    """
    Check if deterministic mode is currently enabled.

    Returns:
        True if deterministic mode is enabled, False otherwise
    """
    return _deterministic_mode


def get_deterministic_seed() -> int:
    """
    Get the deterministic seed value for reproducible execution.

    The seed is determined by (in order of priority):
    1. Explicitly set value via set_deterministic_seed()
    2. AGDD_DETERMINISTIC_SEED environment variable
    3. Derived from current timestamp (for new runs)

    Returns:
        Integer seed value for random number generation
    """
    global _deterministic_seed

    if _deterministic_seed is not None:
        return _deterministic_seed

    # Check environment variable
    env_seed = os.getenv("AGDD_DETERMINISTIC_SEED")
    if env_seed is not None:
        try:
            return int(env_seed)
        except ValueError:
            pass

    # Generate seed from current timestamp for reproducibility within a session
    # Use a stable seed based on process start time rounded to the minute
    timestamp = int(time.time() / 60) * 60  # Round to minute
    return timestamp


def set_deterministic_seed(seed: int) -> None:
    """
    Explicitly set the deterministic seed value.

    Args:
        seed: Integer seed value to use for deterministic execution
    """
    global _deterministic_seed
    _deterministic_seed = seed


def snapshot_environment() -> dict[str, Any]:
    """
    Capture current environment state for replay purposes.

    Creates a snapshot of relevant environment variables, system state,
    and configuration that may affect agent execution.

    Returns:
        Dictionary containing environment snapshot with keys:
        - timestamp: Current Unix timestamp
        - seed: Current deterministic seed
        - deterministic_mode: Whether deterministic mode is enabled
        - env_vars: Relevant environment variables
        - python_random_state: Current random module state (if deterministic)
    """
    snapshot: dict[str, Any] = {
        "timestamp": time.time(),
        "seed": get_deterministic_seed(),
        "deterministic_mode": _deterministic_mode,
        "env_vars": {},
    }

    # Capture relevant environment variables
    env_keys = [
        "AGDD_DETERMINISTIC_SEED",
        "AGDD_ENABLE_MCP",
        "AGDD_LOG_LEVEL",
        "AGDD_BASE_DIR",
    ]
    for key in env_keys:
        value = os.getenv(key)
        if value is not None:
            snapshot["env_vars"][key] = value

    # If deterministic mode is enabled, capture random state
    if _deterministic_mode:
        try:
            snapshot["python_random_state"] = random.getstate()
        except Exception:
            # Gracefully handle any issues with state capture
            pass

    return snapshot


def apply_deterministic_settings(provider_config: dict[str, Any]) -> dict[str, Any]:
    """
    Apply deterministic settings to a provider configuration.

    When deterministic mode is enabled, modifies the provider configuration
    to ensure reproducible execution by:
    - Setting temperature to 0
    - Applying fixed seed values
    - Disabling randomness-inducing features

    Args:
        provider_config: Provider configuration dictionary to modify

    Returns:
        Modified provider configuration with deterministic settings applied.
        Returns a deep copy to avoid mutating the original config.
    """
    # Always create a deep copy to avoid mutating the original
    config = copy.deepcopy(provider_config)

    if not _deterministic_mode:
        return config

    # Apply deterministic settings
    seed = get_deterministic_seed()

    # Set temperature to 0 for deterministic outputs
    config["temperature"] = 0.0

    # Add seed if supported by provider
    config["seed"] = seed

    # Disable top_p sampling (use greedy decoding)
    if "top_p" in config:
        config["top_p"] = 1.0

    # Add metadata indicating deterministic mode
    if "metadata" not in config:
        config["metadata"] = {}
    config["metadata"]["deterministic_mode"] = True
    config["metadata"]["deterministic_seed"] = seed

    return config


def create_replay_context(
    replay_snapshot: dict[str, Any],
    additional_context: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Create execution context from a replay snapshot.

    Prepares context dictionary with replay settings that can be passed
    to agent execution to reproduce a previous run.

    Args:
        replay_snapshot: Environment snapshot from a previous run
        additional_context: Optional additional context to merge

    Returns:
        Context dictionary ready for agent execution
    """
    context: dict[str, Any] = {
        "replay_mode": True,
        "replay_timestamp": replay_snapshot.get("timestamp"),
        "replay_seed": replay_snapshot.get("seed"),
    }

    # If snapshot included deterministic mode, restore it
    if replay_snapshot.get("deterministic_mode"):
        set_deterministic_mode(True)
        if "seed" in replay_snapshot:
            set_deterministic_seed(replay_snapshot["seed"])

    # Merge additional context
    if additional_context:
        context.update(additional_context)

    return context


def compute_run_fingerprint(
    agent_slug: str,
    payload: dict[str, Any],
    provider_config: dict[str, Any],
) -> str:
    """
    Compute a fingerprint for a run configuration.

    Creates a stable hash of the agent slug, input payload, and provider config
    to uniquely identify a run configuration for replay purposes.

    Args:
        agent_slug: Agent identifier
        payload: Input payload
        provider_config: Provider configuration

    Returns:
        Hexadecimal fingerprint string
    """
    import json

    # Create stable JSON representation
    components = {
        "agent": agent_slug,
        "payload": payload,
        "config": provider_config,
    }

    # Sort keys for stable serialization
    stable_json = json.dumps(components, sort_keys=True, ensure_ascii=True)

    # Compute SHA256 hash
    fingerprint = hashlib.sha256(stable_json.encode("utf-8")).hexdigest()

    return fingerprint[:16]  # Use first 16 characters for brevity


__all__ = [
    "set_deterministic_mode",
    "get_deterministic_mode",
    "get_deterministic_seed",
    "set_deterministic_seed",
    "snapshot_environment",
    "apply_deterministic_settings",
    "create_replay_context",
    "compute_run_fingerprint",
]
