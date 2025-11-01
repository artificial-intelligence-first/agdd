# Handoff-as-a-Tool

## Overview

Handoff-as-a-Tool provides a standardized interface for agents to delegate work to other agents or systems. It enables cross-platform agent collaboration with policy enforcement, observability, and multi-platform support (AGDD, ADK, OpenAI, Anthropic).

## Key Features

- **Unified Interface**: Single API for delegating to any platform
- **Multi-Platform Support**: AGDD, ADK, OpenAI, Anthropic
- **Platform-Specific Adapters**: Automatic format translation
- **Policy Enforcement**: Approval requirements for sensitive handoffs
- **Request Tracking**: Complete audit trail of delegation requests
- **Error Handling**: Graceful failure and retry capabilities

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              Source Agent (MAG)                             │
│   "I need specialist help with this task"                  │
│                      │                                      │
│                      ▼                                      │
│   handoff(                                                  │
│     target_agent="specialist-sag",                          │
│     task="Analyze customer sentiment",                      │
│     platform="agdd"                                         │
│   )                                                         │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│           Handoff Tool                                      │
│   ┌─────────────────────────────────────────────────┐       │
│   │  1. Create HandoffRequest                       │       │
│   │  2. Check permissions (if evaluator configured) │       │
│   │  3. Select platform adapter                     │       │
│   │  4. Execute handoff                             │       │
│   │  5. Track request and result                    │       │
│   └─────────────────────────────────────────────────┘       │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│        Platform Adapters                                    │
│   ┌─────────────┬─────────────┬─────────────┬───────────┐  │
│   │    AGDD     │     ADK     │   OpenAI    │ Anthropic │  │
│   │   invoke_   │   ADK API   │ Assistants  │   Claude  │  │
│   │   mag/sag   │             │     API     │    API    │  │
│   └─────────────┴─────────────┴─────────────┴───────────┘  │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│              Target Agent/System                            │
│   Receives task, processes, returns result                  │
└─────────────────────────────────────────────────────────────┘
```

## Usage

### Enabling Handoff

Set the feature flag in your environment:

```bash
export AGDD_HANDOFF_ENABLED=true
```

Or in your API config:

```python
from agdd.api.config import Settings

settings = Settings(
    HANDOFF_ENABLED=True,
)
```

### Basic Usage

```python
from agdd.routing.handoff_tool import HandoffTool

# Initialize handoff tool
handoff_tool = HandoffTool()

recent_reviews = ["Great support turnaround", "Rep resolved billing quickly"]

# Delegate to another AGDD agent
result = await handoff_tool.handoff(
    source_agent="main-orchestrator",
    target_agent="specialist-analyzer",
    task="Analyze customer sentiment from recent reviews",
    payload={
        "reviews": recent_reviews,
    },
    context={
        "customer_id": "12345",
        "time_range": "last_7_days",
    },
    platform="agdd",
    run_id="run-123",
)

print(f"Handoff ID: {result['handoff_id']}")
print(f"Status: {result['status']}")
print(f"Result: {result['result']}")
```

`payload` is optional for non-AGDD integrations, but when an `AgentRunner` instance is supplied it is passed directly to the delegated MAG entrypoint.

### Multi-Platform Handoff

```python
# Handoff to ADK agent
adk_result = await handoff_tool.handoff(
    source_agent="agdd-main",
    target_agent="adk-specialist",
    task="Process structured data extraction",
    platform="adk",
)

# Handoff to OpenAI Assistant
openai_result = await handoff_tool.handoff(
    source_agent="agdd-main",
    target_agent="asst_abc123",  # OpenAI Assistant ID
    task="Generate creative content",
    platform="openai",
)

# Handoff to Anthropic Claude
anthropic_result = await handoff_tool.handoff(
    source_agent="agdd-main",
    target_agent="claude-specialist",
    task="Analyze legal documents",
    platform="anthropic",
)
```

### Tool Schema Export

Handoff can be exposed as a tool to LLMs:

```python
# Get tool schema for specific platform
schema = handoff_tool.get_tool_schema(platform="agdd")

# Use schema in LLM tool definition
tools = [
    schema,
    # ... other tools
]

# LLM can now call handoff tool
```

Platform-specific schemas:

#### AGDD Schema
```json
{
  "name": "handoff",
  "description": "Delegate work to another agent or system",
  "parameters": {
    "type": "object",
    "properties": {
      "target_agent": {
        "type": "string",
        "description": "Agent slug or identifier to delegate to"
      },
      "task": {
        "type": "string",
        "description": "Task description for the target agent"
      },
      "context": {
        "type": "object",
        "description": "Additional context to pass to target agent"
      }
    },
    "required": ["target_agent", "task"]
  }
}
```

#### OpenAI Schema
```json
{
  "type": "function",
  "function": {
    "name": "handoff",
    "description": "Delegate task to another agent",
    "parameters": {
      "type": "object",
      "properties": {
        "agent_id": {
          "type": "string",
          "description": "Target agent ID"
        },
        "instructions": {
          "type": "string",
          "description": "Instructions for the target agent"
        }
      },
      "required": ["agent_id", "instructions"]
    }
  }
}
```

## Platform Adapters

### AGDD Adapter

Delegates to native AGDD agents using `invoke_mag()` or `invoke_sag()`:

```python
from agdd.routing.handoff_tool import AGDDHandoffAdapter

adapter = AGDDHandoffAdapter()

# Check platform support
assert adapter.supports_platform("agdd")

# Execute handoff
result = await adapter.execute_handoff(handoff_request)
```

### ADK Adapter

Delegates to Anthropic ADK agents:

```python
from agdd.routing.handoff_tool import ADKHandoffAdapter

adapter = ADKHandoffAdapter()
assert adapter.supports_platform("adk")
```

### OpenAI Adapter

Delegates to OpenAI Assistants or custom agents:

```python
from agdd.routing.handoff_tool import OpenAIHandoffAdapter

adapter = OpenAIHandoffAdapter()
assert adapter.supports_platform("openai")
```

### Anthropic Adapter

Delegates to Anthropic Claude API agents:

```python
from agdd.routing.handoff_tool import AnthropicHandoffAdapter

adapter = AnthropicHandoffAdapter()
assert adapter.supports_platform("anthropic")
```

### Contracts

- Handoff requests follow [`catalog/contracts/handoff_request.schema.json`](../catalog/contracts/handoff_request.schema.json).
- Handoff responses follow [`catalog/contracts/handoff_response.schema.json`](../catalog/contracts/handoff_response.schema.json).

## Request Tracking

All handoff requests are tracked for observability:

```python
# Get handoff by ID
request = handoff_tool.get_handoff(handoff_id)

print(f"Status: {request.status}")
print(f"Source: {request.source_agent}")
print(f"Target: {request.target_agent}")
print(f"Created: {request.created_at}")
print(f"Result: {request.result}")

# List handoffs by source agent
handoffs = handoff_tool.list_handoffs(source_agent="main-orchestrator")

# List handoffs by status
pending = handoff_tool.list_handoffs(status="pending")
completed = handoff_tool.list_handoffs(status="completed")
failed = handoff_tool.list_handoffs(status="failed")
```

## Policy Enforcement

Handoff can integrate with permission evaluator for policy-based control:

```python
from agdd.governance.permission_evaluator import PermissionEvaluator

# Initialize with permission evaluator
evaluator = PermissionEvaluator()
handoff_tool = HandoffTool(permission_evaluator=evaluator)

# Handoff will check policy
try:
    result = await handoff_tool.handoff(
        source_agent="restricted-agent",
        target_agent="sensitive-system",
        task="Access confidential data",
        platform="agdd",
    )
except PermissionError as e:
    print(f"Handoff denied by policy: {e}")
```

Policy configuration ([`catalog/policies/tool_permissions.yaml`](../catalog/policies/tool_permissions.yaml)):

```yaml
tools:
  handoff:
    permission: REQUIRE_APPROVAL

rules:
  # Allow handoffs in development
  - condition:
      environment: development
      tool_name: handoff
    permission: ALWAYS

  # Require approval for cross-platform handoffs
  - condition:
      tool_name: handoff
      context:
        platform: ["openai", "anthropic"]
    permission: REQUIRE_APPROVAL

  # Block handoffs to external systems
  - condition:
      tool_name: handoff
      context:
        target_agent: "external-*"
    permission: NEVER
```

## Handoff Lifecycle

1. **Request**: Source agent calls `handoff()`
2. **Validation**: Validate parameters and platform
3. **Permission Check**: Evaluate policy (if configured)
4. **Approval** (if required): Wait for human approval
5. **Adapter Selection**: Choose platform-specific adapter
6. **Execution**: Adapter executes handoff
7. **Tracking**: Log request and result
8. **Return**: Return result to source agent

### Handoff States

- **pending**: Request created, not yet executed
- **in_progress**: Execution in progress
- **completed**: Successfully completed
- **failed**: Execution failed
- **rejected**: Rejected by policy

## Error Handling

```python
try:
    result = await handoff_tool.handoff(...)
except ValueError as e:
    # Unsupported platform or invalid parameters
    logger.error(f"Invalid handoff request: {e}")
except PermissionError as e:
    # Denied by policy
    logger.warning(f"Handoff denied: {e}")
except Exception as e:
    # Other errors (timeout, network, etc.)
    logger.error(f"Handoff failed: {e}")
```

## Integration with Approval Gate

Handoff-as-a-Tool **enforces** approval requirements when configured with an approval gate. If a policy returns `REQUIRE_APPROVAL`, the handoff will:

1. **Create an approval ticket** with handoff details
2. **Block execution** until approval is granted
3. **Raise PermissionError** if approval is denied or times out
4. **Only proceed** if approval is granted

### Setup

```python
from agdd.governance.approval_gate import ApprovalGate
from agdd.governance.permission_evaluator import PermissionEvaluator

evaluator = PermissionEvaluator()
approval_gate = ApprovalGate(
    permission_evaluator=evaluator,
    default_timeout_minutes=30,
)

handoff_tool = HandoffTool(
    permission_evaluator=evaluator,
    approval_gate=approval_gate,  # Required for approval enforcement
)
```

### Behavior

**With Approval Gate Configured**:
```python
# Handoff requiring approval (per policy)
try:
    result = await handoff_tool.handoff(
        source_agent="main",
        target_agent="external-api",
        task="Submit payment",
        platform="agdd",
        run_id="run-123",
    )
    # Will wait for human approval before proceeding
except PermissionError as e:
    # Raised if approval is denied or times out
    logger.error(f"Handoff blocked: {e}")
```

**Without Approval Gate (Security Error)**:
```python
handoff_tool = HandoffTool(
    permission_evaluator=evaluator,
    approval_gate=None,  # No approval gate!
)

# If policy requires approval, will raise PermissionError
try:
    result = await handoff_tool.handoff(...)
except PermissionError as e:
    # "Approval required but approval gate is not configured"
    logger.error(f"Configuration error: {e}")
```

### Security Guarantees

- ✅ **Approval enforcement is mandatory** - Cannot bypass if policy requires it
- ✅ **Fail-safe design** - Raises error if approval gate is not configured
- ✅ **Complete audit trail** - All approval requests are logged and tracked
- ✅ **Timeout protection** - Handoffs don't hang indefinitely waiting for approval

## Use Cases

### 1. Specialist Delegation (MAG → SAG)

Main agent delegates to specialized sub-agents:

```python
# Main orchestrator
async def orchestrate_offer(candidate_profile):
    # Delegate compensation analysis
    comp_result = await handoff_tool.handoff(
        source_agent="offer-orchestrator-mag",
        target_agent="compensation-advisor-sag",
        task="Calculate compensation package",
        context=candidate_profile,
        platform="agdd",
    )

    # Delegate benefits analysis
    benefits_result = await handoff_tool.handoff(
        source_agent="offer-orchestrator-mag",
        target_agent="benefits-advisor-sag",
        task="Recommend benefits package",
        context=candidate_profile,
        platform="agdd",
    )

    return combine_results(comp_result, benefits_result)
```

### 2. Cross-Platform Collaboration

AGDD agent delegates to external platform:

```python
# AGDD agent uses OpenAI for specific task
result = await handoff_tool.handoff(
    source_agent="agdd-analyst",
    target_agent="asst_creative_writer",
    task="Generate marketing copy",
    context={"product": "...", "audience": "..."},
    platform="openai",
)
```

### 3. Human-in-the-Loop Delegation

Sensitive handoffs require approval:

```python
# Policy: REQUIRE_APPROVAL for financial operations
result = await handoff_tool.handoff(
    source_agent="sales-agent",
    target_agent="payment-processor",
    task="Process refund of $5000",
    context={"order_id": "12345", "amount": 5000},
    platform="agdd",
)
# Waits for approval before executing
```

## Best Practices

### 1. Clear Task Descriptions

Provide explicit, actionable task descriptions:

✅ **Good**: "Analyze customer sentiment from reviews in the last 7 days and identify top 3 pain points"

❌ **Bad**: "Do sentiment stuff"

### 2. Minimal Context

Pass only necessary context:

```python
# Good: Minimal, relevant context
context = {
    "customer_id": "12345",
    "time_range": "7d",
}

# Bad: Excessive context
context = {
    "customer_id": "12345",
    "full_history": [...],  # Too much data
    "internal_notes": [...],  # Sensitive info
}
```

### 3. Error Handling

Always handle handoff failures:

```python
try:
    result = await handoff_tool.handoff(...)
except Exception as e:
    # Fallback logic
    result = execute_locally()
```

### 4. Idempotency

Design handoffs to be idempotent (safe to retry):

```python
# Include idempotency key in context
context = {
    "idempotency_key": f"{run_id}:{step_id}",
    "task_data": {...},
}
```

### 5. Timeout Handling

Set reasonable timeouts for handoffs:

```python
# TODO: Add timeout support
# result = await handoff_tool.handoff(..., timeout=60)
```

## Observability

Handoff events are logged for observability:

```json
{
  "event_type": "handoff.requested",
  "handoff_id": "uuid",
  "source_agent": "main",
  "target_agent": "specialist",
  "platform": "agdd",
  "created_at": "2025-10-31T10:00:00Z"
}
```

```json
{
  "event_type": "handoff.completed",
  "handoff_id": "uuid",
  "status": "completed",
  "duration_ms": 1234,
  "completed_at": "2025-10-31T10:00:01Z"
}
```

## Limitations

1. **No Streaming**: Handoff results are returned in full (no streaming)
2. **No Callback**: No async callback when handoff completes
3. **Platform-Specific Limits**: Each platform has its own constraints
4. **No Transaction Semantics**: Handoff is one-way; no rollback support

## Future Enhancements

- **Streaming Results**: Stream results as they're generated
- **Async Callbacks**: Notify source agent when handoff completes
- **Handoff Chains**: Multi-hop delegation (A → B → C)
- **Bidirectional Communication**: Source and target can exchange messages
- **Handoff Retry**: Automatic retry with exponential backoff
- **Handoff Timeout**: Configurable timeout per handoff
- **Handoff Caching**: Cache results for identical handoffs

## Related Documentation

- [Agent Architecture](./architecture/agents.md)
- [A2A Communication](./guides/a2a-communication.md)
- [Approval Gate](./approval.md)
- [Permission Evaluator](./governance/permission_evaluator.md)
- [Multi-Provider Support](./guides/multi-provider.md)
