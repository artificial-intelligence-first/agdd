# Remote MCP Client

## Overview

The Remote MCP (Model Context Protocol) Client provides robust, resilient integration with external MCP servers. It supports multiple transport protocols, automatic retry logic with exponential backoff, circuit breaker patterns for fault tolerance, and comprehensive permission management.

## Architecture

### Core Components

1. **AsyncMCPClient**: Async client for invoking remote MCP servers
2. **CircuitBreaker**: Fault tolerance mechanism to prevent cascading failures
3. **RetryConfig**: Exponential backoff with jitter configuration
4. **TransportType**: Support for stdio, WebSocket, and HTTP transports
5. **MCP Decorators**: Convenient decorators for tool integration

### Transport Protocols

- **stdio**: JSON-RPC over stdin/stdout (subprocess communication)
- **websocket**: JSON-RPC over WebSocket (persistent connections)
- **http**: JSON-RPC over HTTP (stateless requests)

## Feature Flag

Remote MCP client is controlled by the `MAGSAG_MCP_ENABLED` feature flag:

```bash
# Enable remote MCP client
export MAGSAG_MCP_ENABLED=true

# Disable remote MCP client (default)
export MAGSAG_MCP_ENABLED=false
```

## Usage

### Basic Client Usage

```python
from magsag.mcp.client import AsyncMCPClient, TransportType

# Create an HTTP-based MCP client
client = AsyncMCPClient(
    server_name="github-api",
    transport=TransportType.HTTP,
    config={
        "url": "https://mcp.github.com",
        "headers": {"Authorization": "Bearer ..."}
    }
)

# Initialize the client
await client.initialize()

# Invoke a tool
result = await client.invoke(
    tool="create_issue",
    args={
        "repo": "org/repo",
        "title": "Bug report",
        "body": "Description of the bug"
    },
    timeout=30.0
)

# Clean up
await client.close()
```

### Retry Configuration

```python
from magsag.mcp.client import RetryConfig

# Custom retry configuration
retry_config = RetryConfig(
    max_attempts=5,          # Retry up to 5 times
    base_delay_ms=200,       # Start with 200ms delay
    max_delay_ms=30000,      # Cap at 30 seconds
    exponential_base=2.0,    # Double delay each retry
    jitter=True              # Add randomness to prevent thundering herd
)

client = AsyncMCPClient(
    server_name="stripe-api",
    transport=TransportType.HTTP,
    config={"url": "https://mcp.stripe.com"},
    retry_config=retry_config
)
```

### Circuit Breaker

```python
from magsag.mcp.client import CircuitBreakerConfig, CircuitState

# Configure circuit breaker
circuit_config = CircuitBreakerConfig(
    failure_threshold=5,      # Open after 5 failures
    success_threshold=2,      # Close after 2 successes in half-open
    timeout_seconds=60,       # Wait 60s before half-open
    half_open_max_calls=1     # Allow 1 test call in half-open
)

client = AsyncMCPClient(
    server_name="external-api",
    transport=TransportType.HTTP,
    config={"url": "https://api.example.com"},
    circuit_breaker_config=circuit_config
)

# Check circuit state
if client.get_circuit_state() == CircuitState.OPEN:
    print("Circuit is open, service is down")

# Manually reset circuit (admin operation)
client.reset_circuit()
```

### Using Decorators

#### @mcp_tool Decorator

```python
from magsag.mcp.decorators import mcp_tool

@mcp_tool(
    server="github",
    tool="create_issue",
    auth={"token": "env://GITHUB_TOKEN"},  # Resolve from environment
    timeout=30.0,
    require_approval=True
)
async def create_github_issue(repo: str, title: str, body: str) -> dict:
    """Create a GitHub issue (implementation replaced by decorator)."""
    pass

# Usage
issue = await create_github_issue(
    repo="org/repo",
    title="Bug Report",
    body="Description..."
)
```

#### @mcp_authenticated Decorator

```python
from magsag.mcp.decorators import mcp_authenticated

@mcp_authenticated(auth_env_var="API_KEY", auth_type="bearer")
async def call_protected_api(auth_header: str) -> dict:
    """Call API with authentication injected."""
    # auth_header is automatically injected from environment
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.example.com/data",
            headers={"Authorization": auth_header}
        )
        return response.json()
```

#### @mcp_cached Decorator

```python
from magsag.mcp.decorators import mcp_cached, mcp_tool

@mcp_cached(ttl_seconds=300)  # Cache for 5 minutes
@mcp_tool(server="github", tool="get_user")
async def get_github_user(username: str) -> dict:
    """Get GitHub user (cached for 5 minutes)."""
    pass

# First call hits the API
user1 = await get_github_user("octocat")

# Second call within 5 minutes uses cache
user2 = await get_github_user("octocat")  # Instant, no API call
```

## Permission Management

### Permission Levels

MCP tools are governed by three permission levels:

- **ALWAYS**: Tool is always allowed without approval
- **REQUIRE_APPROVAL**: Tool requires human approval before execution
- **NEVER**: Tool is never allowed to execute

### Configuration

Permissions are defined in `catalog/policies/mcp_permissions.yaml`:

```yaml
# Default: require approval for all MCP operations
default_permission: REQUIRE_APPROVAL

# Tool-specific permissions
tools:
  "github.get_user":
    permission: ALWAYS
    description: "Read-only operation"

  "github.create_issue":
    permission: REQUIRE_APPROVAL
    description: "Write operation"

  "github.delete_repo":
    permission: NEVER
    description: "Destructive operation"
```

### Environment-Specific Overrides

```yaml
environments:
  development:
    default_permission: ALWAYS  # Relaxed for dev
    overrides:
      "github.delete_repo": NEVER

  production:
    default_permission: REQUIRE_APPROVAL  # Strict for prod
    overrides:
      "github.get_user": ALWAYS
```

### Context-Based Rules

```yaml
context_rules:
  - name: "safe_repo_operations"
    condition:
      tool_pattern: "github.*"
      args_match:
        repo: "*/test-*"  # Test repos only
    permission: ALWAYS

  - name: "small_charges"
    condition:
      tool: "stripe.charge"
      args_match:
        amount_usd:
          less_than: 10.0
    permission: ALWAYS
```

## Authentication

### Environment Variables

```bash
# Store credentials in environment
export GITHUB_TOKEN="ghp_xxxxxxxxxxxx"
export STRIPE_API_KEY="sk_test_xxxxxxxx"
export DATABASE_URL="postgresql://user:pass@localhost/db"
```

### Secrets Resolution

```python
from magsag.mcp.decorators import resolve_secret

# Resolve from environment
token = resolve_secret("env://GITHUB_TOKEN")

# Resolve from secrets manager (placeholder for future)
# secret = resolve_secret("secrets://path/to/secret")

# Plain value (no resolution)
value = resolve_secret("plain_text")
```

## Resilience Patterns

### Exponential Backoff with Jitter

Prevents thundering herd problem when services recover:

```
Attempt 1: 100ms
Attempt 2: 200ms ± 25% jitter
Attempt 3: 400ms ± 25% jitter
Attempt 4: 800ms ± 25% jitter
...
```

### Circuit Breaker States

```
CLOSED (normal) ──[5 failures]──> OPEN (failing)
                                      │
                                      │ [60s timeout]
                                      ↓
                             HALF_OPEN (testing)
                                   ╱    ╲
                   [2 successes] ╱        ╲ [1 failure]
                               ╱            ╲
                          CLOSED            OPEN
```

### Timeout Handling

```python
try:
    result = await client.invoke(
        tool="slow_operation",
        args={},
        timeout=5.0  # 5 second timeout
    )
except MCPTimeoutError:
    logger.error("Operation timed out")
    # Handle timeout gracefully
```

## Error Handling

### Exception Hierarchy

```
MCPClientError (base)
├── MCPTimeoutError
├── MCPCircuitOpenError
└── MCPTransportError
```

### Example

```python
from magsag.mcp.client import (
    MCPClientError,
    MCPTimeoutError,
    MCPCircuitOpenError,
)

try:
    result = await client.invoke("tool", {})
except MCPTimeoutError:
    # Handle timeout
    logger.error("Request timed out")
except MCPCircuitOpenError:
    # Handle circuit open
    logger.error("Service is down, circuit breaker is open")
except MCPClientError as e:
    # Handle other MCP errors
    logger.error(f"MCP error: {e}")
```

## Observability

### Logging

```python
import logging

# Enable debug logging for MCP client
logging.getLogger("magsag.mcp.client").setLevel(logging.DEBUG)

# Logs:
# - Client initialization
# - Tool invocations (with timing)
# - Retry attempts
# - Circuit state transitions
# - Errors and timeouts
```

### Metrics

MCP operations are automatically tracked:

```python
# Logged to unified storage
await storage.append_event(
    run_id=run_id,
    agent_slug=agent_slug,
    event_type="mcp.call",
    payload={
        "server": "github",
        "tool": "create_issue",
        "duration_ms": 234,
        "success": True
    }
)
```

## Best Practices

### 1. Use Appropriate Timeouts

```python
# Short timeout for fast operations
result = await client.invoke("get_user", {}, timeout=5.0)

# Longer timeout for slow operations
result = await client.invoke("generate_report", {}, timeout=60.0)
```

### 2. Handle Circuit Breaker States

```python
if client.get_circuit_state() == CircuitState.OPEN:
    # Provide fallback or skip operation
    return cached_result

result = await client.invoke("tool", {})
```

### 3. Configure Retry Appropriately

```python
# Idempotent operations: more retries OK
idempotent_retry = RetryConfig(max_attempts=5)

# Non-idempotent operations: fewer retries
write_retry = RetryConfig(max_attempts=2)
```

### 4. Cache Read Operations

```python
@mcp_cached(ttl_seconds=300)
@mcp_tool(server="github", tool="get_repo")
async def get_repo(name: str) -> dict:
    pass
```

### 5. Use Context-Based Permissions

```python
# In mcp_permissions.yaml
context_rules:
  - name: "safe_operations"
    condition:
      tool_pattern: "*.get_*"  # All read operations
    permission: ALWAYS
```

## Configuration Examples

### GitHub MCP Server

```python
github_client = AsyncMCPClient(
    server_name="github",
    transport=TransportType.HTTP,
    config={
        "url": "https://api.github.com",
        "headers": {
            "Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}",
            "Accept": "application/vnd.github+json"
        }
    },
    retry_config=RetryConfig(max_attempts=3),
    circuit_breaker_config=CircuitBreakerConfig(
        failure_threshold=5,
        timeout_seconds=60
    )
)
```

### PostgreSQL MCP Server (stdio)

```python
postgres_client = AsyncMCPClient(
    server_name="postgres",
    transport=TransportType.STDIO,
    config={
        "command": ["mcp-server-postgres"],
        "env": {
            "DATABASE_URL": os.getenv("DATABASE_URL")
        }
    }
)
```

### Stripe MCP Server

```python
stripe_client = AsyncMCPClient(
    server_name="stripe",
    transport=TransportType.HTTP,
    config={
        "url": "https://api.stripe.com/v1",
        "headers": {
            "Authorization": f"Bearer {os.getenv('STRIPE_API_KEY')}"
        }
    },
    retry_config=RetryConfig(
        max_attempts=2,  # Financial operations: fewer retries
        base_delay_ms=500
    )
)
```

## Troubleshooting

### Circuit Breaker Stuck Open

```python
# Check circuit state
print(client.get_circuit_state())

# Manually reset (admin operation)
client.reset_circuit()
```

### Timeout Issues

```python
# Increase timeout
result = await client.invoke("slow_tool", {}, timeout=120.0)

# Or reduce retry attempts
retry_config = RetryConfig(max_attempts=1)
```

### Authentication Errors

```bash
# Verify environment variables are set
env | grep TOKEN

# Test secret resolution
from magsag.mcp.decorators import resolve_secret
print(resolve_secret("env://GITHUB_TOKEN"))
```

## Future Enhancements

- **WebSocket Support**: Full implementation of WebSocket transport
- **Streaming**: Support for streaming responses
- **Connection Pooling**: Reuse connections for HTTP transport
- **Adaptive Timeouts**: Automatically adjust timeouts based on observed latency
- **Distributed Circuit Breaker**: Share circuit state across instances

## References

- [MCP Specification](https://modelcontextprotocol.io)
- [Permission Policies](../catalog/policies/mcp_permissions.yaml)
- [Approval Gate](./approval.md)
- [API Reference](./api/mcp.md)
