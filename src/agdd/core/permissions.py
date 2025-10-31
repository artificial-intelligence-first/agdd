"""
Permission models for approval-as-a-policy workflow.

Defines tool permission levels and approval ticket structures for
controlling agent actions that require human oversight.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


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
    requested_at: datetime
    expires_at: datetime
    status: str  # pending, approved, denied, expired
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    response: Optional[Dict[str, Any]] = None
