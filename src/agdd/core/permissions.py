"""
Permission models for approval-as-a-policy workflow.

Defines tool permission levels, approval ticket structures, and helper
utilities for governing agent actions that require human oversight.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, date
from enum import Enum
from typing import Any, Dict, Optional, Literal, cast


class ToolPermission(str, Enum):
    """
    Tool execution permission levels.

    - ALWAYS: Tool is always allowed to execute without approval
    - REQUIRE_APPROVAL: Tool execution requires human approval
    - NEVER: Tool is never allowed to execute
    """

    ALWAYS = "always"
    REQUIRE_APPROVAL = "require_approval"
    NEVER = "never"


ApprovalStatus = Literal["pending", "approved", "denied", "expired"]


@dataclass
class ApprovalTicket:
    """
    Approval ticket for pending tool execution requests.

    Tracks the lifecycle of a tool execution that requires approval,
    from creation through resolution (approved/denied) or expiration.
    """

    ticket_id: str
    run_id: str
    agent_slug: str
    tool_name: str
    tool_args: Dict[str, Any]
    args_hash: str
    requested_at: datetime
    expires_at: datetime
    status: ApprovalStatus  # pending, approved, denied, expired
    masked_args: Dict[str, Any] = field(default_factory=dict)
    step_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    decision_reason: Optional[str] = None
    response: Optional[Dict[str, Any]] = None


# Redaction placeholder used when masking potentially sensitive values
REDACTED = "***redacted***"

# Keywords (case-insensitive) that trigger masking when found in argument keys
SENSITIVE_KEYWORDS = {
    "password",
    "passphrase",
    "secret",
    "token",
    "key",
    "credential",
    "auth",
    "api",
    "session",
    "signature",
    "cookie",
    "bearer",
}


def _should_mask(key: Optional[str], value: Any) -> bool:
    """Determine whether a value should be masked based on heuristics."""
    if key:
        lowered = key.lower()
        if any(keyword in lowered for keyword in SENSITIVE_KEYWORDS):
            return True

    # Mask long single-token strings (likely secrets) even without key hints
    if isinstance(value, str):
        if len(value) >= 32 and " " not in value:
            return True
    return False


def mask_tool_args(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a masked copy of tool arguments with sensitive values redacted.

    Args:
        args: Original tool arguments

    Returns:
        Dict with potentially sensitive values replaced by REDACTED marker.
    """

    def _mask(value: Any, key_hint: Optional[str] = None) -> Any:
        if isinstance(value, dict):
            return {k: _mask(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [_mask(item, key_hint) for item in value]
        if isinstance(value, tuple):
            return tuple(_mask(item, key_hint) for item in value)
        if isinstance(value, (set, frozenset)):
            return [_mask(item, key_hint) for item in value]
        if _should_mask(key_hint, value):
            return REDACTED
        return value

    return cast(Dict[str, Any], _mask(args))


def _normalize_for_hash(value: Any) -> Any:
    """
    Normalize values into JSON-serializable representation for hashing.

    Ensures deterministic ordering for dicts/lists and renders datetime objects.
    """
    if isinstance(value, dict):
        return {k: _normalize_for_hash(value[k]) for k in sorted(value)}
    if isinstance(value, list):
        return [_normalize_for_hash(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_for_hash(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_normalize_for_hash(item) for item in value)
    if isinstance(value, datetime):
        ts = value if value.tzinfo else value.replace(tzinfo=UTC)
        return ts.astimezone(UTC).isoformat()
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC).isoformat()
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    # Fallback to string representation for unsupported types
    return str(value)


def compute_args_hash(args: Dict[str, Any]) -> str:
    """
    Compute deterministic SHA-256 hash for tool arguments.

    Args:
        args: Tool arguments to hash

    Returns:
        Hex-encoded SHA-256 digest
    """
    normalized = _normalize_for_hash(args)
    serialized = json.dumps(normalized, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
