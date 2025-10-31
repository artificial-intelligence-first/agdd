# Approval-as-a-Policy

## Overview

Approval-as-a-Policy is a governance feature that enables human oversight for critical agent actions. It provides a flexible policy-driven framework for requiring approval before executing sensitive tools or operations.

## Key Features

- **Policy-Driven**: Define tool permissions (ALWAYS, REQUIRE_APPROVAL, NEVER) via YAML policies
- **Approval Lifecycle**: Complete ticket management from creation to resolution
- **Real-Time Notifications**: Server-Sent Events (SSE) for live approval status updates
- **REST API**: Full CRUD operations for approval tickets
- **Timeout Handling**: Automatic expiration of pending approvals
- **Idempotent Operations**: Safe retries and replay capabilities

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent Execution                          │
│   ┌──────────────────────────────────────────────────┐      │
│   │  Tool Call Request                               │      │
│   └──────────────┬───────────────────────────────────┘      │
└──────────────────┼──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│             Permission Evaluator                            │
│   - Load policies from catalog/policies/                    │
│   - Evaluate tool permission (ALWAYS/REQUIRE_APPROVAL/NEVER)│
│   - Apply context-based rules and overrides                 │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│              Approval Gate                                  │
│   ┌─────────────────────────────────────────────────┐       │
│   │  Permission = REQUIRE_APPROVAL                  │       │
│   │    ↓                                            │       │
│   │  1. Create approval ticket                      │       │
│   │  2. Emit SSE event (approval.required)          │       │
│   │  3. Wait for decision (polling/SSE)             │       │
│   │  4. Execute tool if approved                    │       │
│   └─────────────────────────────────────────────────┘       │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│              HTTP API                                       │
│   - GET  /runs/{run_id}/approvals                          │
│   - GET  /runs/{run_id}/approvals/{approval_id}            │
│   - POST /runs/{run_id}/approvals/{approval_id}            │
│   - GET  /runs/{run_id}/approvals/{approval_id}/events (SSE)│
└─────────────────────────────────────────────────────────────┘
```

## Usage

### Enabling Approvals

Set the feature flag in your environment:

```bash
export APPROVALS_ENABLED=true
export APPROVAL_TTL_MIN=30  # Ticket timeout in minutes
```

Or in your API config:

```python
from agdd.api.config import Settings

settings = Settings(
    APPROVALS_ENABLED=True,
    APPROVAL_TTL_MIN=30,
)
```

### Policy Configuration

Define tool permissions in `catalog/policies/tool_permissions.yaml`:

```yaml
# Default permission for all tools
default: REQUIRE_APPROVAL

# Tool-specific permissions
tools:
  # Safe read-only tools
  read_file:
    permission: ALWAYS

  list_directory:
    permission: ALWAYS

  # Dangerous tools requiring approval
  execute_command:
    permission: REQUIRE_APPROVAL

  delete_file:
    permission: REQUIRE_APPROVAL

  # Forbidden tools
  format_disk:
    permission: NEVER

# Context-based rules
rules:
  # Allow certain tools in development
  - condition:
      environment: development
      tool_pattern: "test_*"
    permission: ALWAYS

  # Require approval for production writes
  - condition:
      environment: production
      tool_pattern: "write_*"
    permission: REQUIRE_APPROVAL
```

### Programmatic Usage

```python
from agdd.governance.approval_gate import ApprovalGate
from agdd.governance.permission_evaluator import PermissionEvaluator

# Initialize components
permission_evaluator = PermissionEvaluator()
approval_gate = ApprovalGate(
    permission_evaluator=permission_evaluator,
    default_timeout_minutes=30,
)

# Execute tool with approval check
async def execute_with_approval():
    result = await approval_gate.execute_with_approval(
        run_id="run-123",
        agent_slug="my-agent",
        tool_name="delete_file",
        tool_args={"path": "/tmp/test.txt"},
        tool_fn=actual_delete_function,
        context={"environment": "production"},
    )
    return result
```

### API Usage

#### List Pending Approvals

```bash
curl -H "Authorization: Bearer $API_KEY" \
  http://localhost:8000/api/v1/runs/run-123/approvals
```

Response:
```json
{
  "tickets": [
    {
      "ticket_id": "ticket-uuid",
      "run_id": "run-123",
      "agent_slug": "my-agent",
      "tool_name": "delete_file",
      "tool_args": {"path": "/tmp/test.txt"},
      "status": "pending",
      "requested_at": "2025-10-31T10:00:00Z",
      "expires_at": "2025-10-31T10:30:00Z"
    }
  ],
  "count": 1
}
```

#### Get Approval Details

```bash
curl -H "Authorization: Bearer $API_KEY" \
  http://localhost:8000/api/v1/runs/run-123/approvals/ticket-uuid
```

#### Approve Ticket

```bash
curl -X POST \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "approve",
    "resolved_by": "admin@example.com",
    "response": {"note": "Approved after review"}
  }' \
  http://localhost:8000/api/v1/runs/run-123/approvals/ticket-uuid
```

#### Deny Ticket

```bash
curl -X POST \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "deny",
    "resolved_by": "admin@example.com",
    "reason": "Security concern"
  }' \
  http://localhost:8000/api/v1/runs/run-123/approvals/ticket-uuid
```

#### Stream Approval Events (SSE)

```bash
curl -N -H "Authorization: Bearer $API_KEY" \
  http://localhost:8000/api/v1/runs/run-123/approvals/ticket-uuid/events
```

SSE events:
```
event: approval.required
data: {"ticket_id": "...", "status": "pending", ...}

event: approval.updated
data: {"ticket_id": "...", "status": "approved", ...}
```

## Permission Levels

### ALWAYS
Tool is always allowed without approval. Use for safe, read-only operations.

**Example**: `read_file`, `list_directory`, `get_status`

### REQUIRE_APPROVAL
Tool requires human approval before execution. Use for write operations, external API calls, or sensitive actions.

**Example**: `delete_file`, `execute_command`, `send_email`, `charge_payment`

### NEVER
Tool is forbidden and will never be executed. Use for dangerous operations.

**Example**: `format_disk`, `drop_database`, `shutdown_system`

## Approval Lifecycle

1. **Request**: Agent attempts to execute tool
2. **Evaluation**: Permission evaluator checks policy
3. **Ticket Creation**: If REQUIRE_APPROVAL, create approval ticket
4. **Notification**: Emit SSE event (approval.required)
5. **Wait**: Agent polls for decision or listens to SSE
6. **Resolution**: Human approves or denies via API
7. **Execution**: If approved, tool executes; if denied, error raised
8. **Cleanup**: Ticket marked as resolved or expired

## Timeout Handling

Approval tickets automatically expire after the configured timeout (default 30 minutes):

- **Pending → Expired**: Ticket expires if not resolved in time
- **ApprovalTimeoutError**: Raised when waiting for expired ticket
- **Cleanup**: Expired tickets can be cleaned up with `expire_old_tickets()`

## Error Handling

```python
from agdd.governance.approval_gate import (
    ApprovalDeniedError,
    ApprovalTimeoutError,
    ApprovalGateError,
)

try:
    result = await approval_gate.execute_with_approval(...)
except ApprovalDeniedError:
    # Approval was explicitly denied
    logger.info("Operation denied by approver")
except ApprovalTimeoutError:
    # Approval request timed out
    logger.warning("Approval timeout, operation cancelled")
except ApprovalGateError as e:
    # Other approval gate errors
    logger.error(f"Approval gate error: {e}")
```

## Best Practices

### Policy Design

1. **Default to REQUIRE_APPROVAL**: Better safe than sorry
2. **Explicitly Allow Safe Operations**: Use ALWAYS for read-only tools
3. **Never Allow Dangerous Operations**: Use NEVER for destructive actions
4. **Use Context Rules**: Apply environment-specific permissions
5. **Document Policies**: Add comments explaining each permission

### Timeout Configuration

- **Development**: Short timeouts (5-10 minutes) for fast iteration
- **Production**: Longer timeouts (30-60 minutes) for human review
- **Automated Systems**: Consider using background approval workflows

### Error Handling

- **Graceful Degradation**: Handle ApprovalDeniedError appropriately
- **User Feedback**: Inform users why operations require approval
- **Audit Trail**: Log all approval requests and decisions

### Security

- **Authentication**: Always require authentication for approval endpoints
- **Authorization**: Verify approver has appropriate permissions
- **Audit Logging**: Record who approved/denied each ticket
- **Rate Limiting**: Prevent abuse of approval API

## Observability

Approval events are automatically logged to observability systems:

```json
{
  "event_type": "approval.required",
  "run_id": "run-123",
  "agent_slug": "my-agent",
  "tool_name": "delete_file",
  "ticket_id": "ticket-uuid",
  "requested_at": "2025-10-31T10:00:00Z"
}
```

## Storage Backend

Approval tickets can be stored in:

- **In-Memory**: Default for development (not persistent)
- **SQLite**: Persistent storage with FTS5 search
- **PostgreSQL**: Production-grade storage with ACID compliance

Configure storage backend:

```python
from agdd.storage.backends.sqlite import SQLiteStorageBackend

storage = SQLiteStorageBackend(db_path=".agdd/storage.db")
await storage.initialize()

approval_gate = ApprovalGate(
    permission_evaluator=permission_evaluator,
    ticket_store=storage,
)
```

## Future Enhancements

- **Approval Workflows**: Multi-step approval chains
- **Role-Based Approvals**: Different approvers for different tool categories
- **Approval Policies**: Time-based, threshold-based approval rules
- **Webhook Integration**: Notify external systems of approval requests
- **Slack/Teams Integration**: Approve directly from chat platforms

## Related Documentation

- [Permission Evaluator](./governance/permission_evaluator.md)
- [Storage Layer](./storage.md)
- [API Usage](./guides/api-usage.md)
- [Security Policies](./policies/security.md)
