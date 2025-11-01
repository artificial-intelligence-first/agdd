# Memory IR Layer

## Overview

The Memory IR (Intermediate Representation) layer provides structured, persistent memory storage for MAGSAG agents. It enables agents to maintain context across runs, share information across agent boundaries, and implement sophisticated memory management strategies with built-in governance, TTL, and PII handling.

## Architecture

### Core Components

1. **MemoryEntry**: Pydantic model representing a single memory entry
2. **MemoryScope**: Enum defining memory visibility and lifetime
3. **AbstractMemoryStore**: Abstract base class for storage backends
4. **SQLiteMemoryStore**: SQLite-based implementation (development)
5. **PostgresMemoryStore**: PostgreSQL-based implementation (production)

Memory entry payloads follow [`catalog/contracts/memory_entry.schema.json`](../catalog/contracts/memory_entry.schema.json), ensuring consistent validation across storage backends and catalog tooling.

### Memory Scopes

Memory entries are organized by scope, which determines their lifetime and visibility:

- **SESSION**: Ephemeral memory tied to a single run
  - Requires `run_id`
  - Default TTL: 1 hour
  - Automatically cleaned up after run completion
  - Example: Intermediate computation results, temporary context

- **LONG_TERM**: Persistent memory for a specific agent
  - Survives across runs
  - Default TTL: 30 days
  - Example: User preferences, learned patterns, agent state

- **ORG**: Organization-wide shared memory
  - Accessible across all agents
  - Default TTL: 90 days
  - Example: Global configuration, shared knowledge base

## Usage

### Feature Flag

Memory IR is controlled by the `MAGSAG_MEMORY_ENABLED` feature flag:

```bash
# Enable memory IR
export MAGSAG_MEMORY_ENABLED=true

# Disable memory IR (default, maintains backward compatibility)
export MAGSAG_MEMORY_ENABLED=false
```

### Runner Integration

When `MAGSAG_MEMORY_ENABLED` is active (or `enable_memory=True` is passed to `AgentRunner`), MAG and SAG executions automatically persist session-scoped `input` and `output` memories. Use `await runner.load_memories(...)` inside agents to retrieve recent context or `await runner.save_memory(...)` for durable entries.

### Creating Memory Entries

```python
from magsag.core.memory import create_memory, MemoryScope

# Create a session-scoped memory
session_memory = create_memory(
    scope=MemoryScope.SESSION,
    agent_slug="my-agent",
    run_id="run-abc123",
    key="task_context",
    value={
        "user_query": "Implement feature X",
        "current_step": "analysis"
    },
    ttl_seconds=3600,  # 1 hour
    tags=["task", "context"]
)

# Create a long-term memory
user_prefs = create_memory(
    scope=MemoryScope.LONG_TERM,
    agent_slug="my-agent",
    key="user_preferences",
    value={
        "theme": "dark",
        "language": "python",
        "verbosity": "detailed"
    },
    retention_policy="production",
    tags=["preferences"]
)

# Create an org-wide shared memory
org_config = create_memory(
    scope=MemoryScope.ORG,
    agent_slug="config-agent",
    key="api_limits",
    value={
        "max_requests_per_minute": 100,
        "max_tokens_per_request": 4096
    },
    retention_policy="permanent"
)
```

### Working with Storage Backends

```python
from magsag.storage.memory_store import SQLiteMemoryStore

# Initialize SQLite store (development)
store = SQLiteMemoryStore(
    db_path=".magsag/memory.db",
    enable_fts=True  # Enable full-text search
)
await store.initialize()

# Create a memory entry
await store.create_memory(session_memory)

# Retrieve a memory
entry = await store.get_memory(memory_id)

# Update a memory
entry.value["current_step"] = "implementation"
await store.update_memory(entry)

# List memories with filters
memories = await store.list_memories(
    scope=MemoryScope.LONG_TERM,
    agent_slug="my-agent",
    tags=["preferences"]
)

# Full-text search
results = await store.search_memories(
    query="python",
    scope=MemoryScope.LONG_TERM
)

# Clean up
await store.close()
```

### PostgreSQL Backend (Production)

```python
from magsag.storage.memory_store import PostgresMemoryStore

# Initialize PostgreSQL store
store = PostgresMemoryStore(
    dsn="postgresql://user:pass@localhost/magsag"
)
await store.initialize()

# API is identical to SQLite
await store.create_memory(entry)
# ...
```

## PII Handling

The Memory IR layer includes built-in PII (Personally Identifiable Information) tagging and governance:

### Supported PII Tags

- `email`: Email addresses
- `phone`: Phone numbers
- `ssn`: Social Security Numbers
- `name`: Full names
- `address`: Physical addresses
- `credit_card`: Credit card numbers
- `ip_address`: IP addresses
- `biometric`: Biometric data
- `health`: Health/medical information (HIPAA)
- `financial`: Financial information

### Usage

```python
# Create memory with PII tags
user_data = create_memory(
    scope=MemoryScope.LONG_TERM,
    agent_slug="my-agent",
    key="user_contact",
    value={
        "email": "user@example.com",
        "phone": "+1-555-0123"
    },
    pii_tags=["email", "phone"],
    retention_policy="compliance"
)
```

### PII Retention Rules

PII-tagged memories are subject to automatic retention policies defined in `catalog/policies/retention_policy.yaml`:

- **Critical PII** (SSN, credit card, biometric, health):
  - Maximum TTL: 30 days
  - Auto-delete on run completion for SESSION scope
  - Requires approval for TTL extension

- **High-risk PII** (email, phone, address, financial):
  - Maximum TTL: 90 days

- **Medium/low-risk PII** (name, IP address):
  - Maximum TTL: 365 days

## Retention Policies

Memory entries can reference named retention policies defined in `catalog/policies/retention_policy.yaml`:

### Available Policies

- **dev**: Short-lived (1 hour) for development/testing
- **production**: Standard retention (30 days)
- **compliance**: Extended retention (365 days) for audit
- **ephemeral**: Immediate expiration after run
- **permanent**: No automatic expiration

### Usage

```python
# Use a named retention policy
memory = create_memory(
    scope=MemoryScope.LONG_TERM,
    agent_slug="my-agent",
    key="audit_log",
    value={"action": "data_access", "timestamp": "..."},
    retention_policy="compliance"
)
```

## Lifecycle Management

### TTL (Time-To-Live)

```python
# Set TTL explicitly
memory.set_ttl(3600)  # 1 hour

# Check if expired
if memory.is_expired():
    print("Memory has expired")

# Apply default TTL for scope
from magsag.core.memory import apply_default_ttl

ttl = apply_default_ttl(MemoryScope.SESSION)  # 3600 seconds
```

### Expiration and Cleanup

```python
# Manually expire old memories
count = await store.expire_old_memories()
print(f"Deleted {count} expired memories")

# Vacuum old memories (retention-based cleanup)
report = await store.vacuum(
    scope=MemoryScope.SESSION,
    older_than_days=7,
    dry_run=True  # Preview what would be deleted
)
print(f"Would delete: {report['would_delete_count']} memories")

# Perform actual cleanup
report = await store.vacuum(
    older_than_days=90,
    dry_run=False
)
```

## Best Practices

### 1. Choose the Right Scope

- Use **SESSION** for temporary, run-specific data
- Use **LONG_TERM** for agent-specific persistent data
- Use **ORG** sparingly for truly global configuration

### 2. Set Appropriate TTLs

```python
# Good: Explicit TTL for session data
temp_data = create_memory(
    scope=MemoryScope.SESSION,
    agent_slug="my-agent",
    run_id=run_id,
    key="temp_result",
    value=result,
    ttl_seconds=3600  # Clean up after 1 hour
)

# Good: Use named policy for compliance
audit_log = create_memory(
    scope=MemoryScope.LONG_TERM,
    agent_slug="my-agent",
    key="access_log",
    value=log_entry,
    retention_policy="compliance"  # 365 days
)
```

### 3. Tag PII Appropriately

```python
# Good: Tag all PII fields
user_profile = create_memory(
    scope=MemoryScope.LONG_TERM,
    agent_slug="my-agent",
    key="user_profile",
    value={
        "name": "John Doe",
        "email": "john@example.com",
        "preferences": {"theme": "dark"}
    },
    pii_tags=["name", "email"]  # Only PII fields
)
```

### 4. Use Tags for Organization

```python
# Good: Use descriptive tags
memory = create_memory(
    scope=MemoryScope.LONG_TERM,
    agent_slug="my-agent",
    key="experiment_results",
    value=results,
    tags=["experiment", "ml", "production"]
)

# Later: Query by tags
ml_memories = await store.list_memories(tags=["ml", "production"])
```

### 5. Clean Up Session Memories

```python
async def cleanup_run_memories(run_id: str, store: AbstractMemoryStore) -> None:
    """Clean up all session memories for a completed run."""
    memories = await store.list_memories(
        scope=MemoryScope.SESSION,
        run_id=run_id
    )

    for memory in memories:
        await store.delete_memory(memory.memory_id)
```

## Integration with MAG/SAG

### MAG (Master Agent) Usage

```python
# MAG creates session-scoped context for delegation
async def delegate_task(mag_agent: Agent, task: str) -> None:
    # Store delegation context
    context = create_memory(
        scope=MemoryScope.SESSION,
        agent_slug=mag_agent.slug,
        run_id=mag_agent.run_id,
        key=f"delegation_{task_id}",
        value={
            "task": task,
            "delegated_to": "sag-worker",
            "started_at": datetime.utcnow().isoformat()
        },
        tags=["delegation", "task"]
    )

    await memory_store.create_memory(context)
```

### SAG (Sub-Agent) Usage

```python
# SAG accesses parent MAG context
async def execute_subtask(sag_agent: Agent, parent_run_id: str) -> None:
    # Read parent context
    contexts = await memory_store.list_memories(
        scope=MemoryScope.SESSION,
        run_id=parent_run_id,
        tags=["delegation"]
    )

    # Store own results
    result = create_memory(
        scope=MemoryScope.SESSION,
        agent_slug=sag_agent.slug,
        run_id=sag_agent.run_id,
        key="subtask_result",
        value={"status": "completed", "output": output},
        tags=["result"]
    )

    await memory_store.create_memory(result)
```

## Observability

Memory operations are automatically logged to the unified storage layer:

```python
# Memory writes generate events
await storage.append_event(
    run_id=run_id,
    agent_slug=agent_slug,
    event_type="memory.write",
    timestamp=datetime.utcnow(),
    level="info",
    message=f"Created memory: {memory.key}",
    payload={
        "memory_id": memory.memory_id,
        "scope": memory.scope.value,
        "key": memory.key,
        "has_pii": len(memory.pii_tags) > 0
    }
)
```

## Migration Guide

### From File-Based Storage

```python
# Before: File-based state
with open(f".state/{agent_slug}.json", "w") as f:
    json.dump(state, f)

# After: Memory IR
memory = create_memory(
    scope=MemoryScope.LONG_TERM,
    agent_slug=agent_slug,
    key="agent_state",
    value=state
)
await memory_store.create_memory(memory)
```

### From In-Memory Caching

```python
# Before: In-memory dict
cache = {}
cache[key] = value

# After: Memory IR with SESSION scope
memory = create_memory(
    scope=MemoryScope.SESSION,
    agent_slug=agent_slug,
    run_id=run_id,
    key=key,
    value=value,
    ttl_seconds=3600
)
await memory_store.create_memory(memory)
```

## Performance Considerations

### SQLite Backend

- **Pros**: Zero configuration, single file, FTS5 search
- **Cons**: Single-writer limitation, not suitable for high concurrency
- **Use Case**: Development, single-agent deployments

### PostgreSQL Backend

- **Pros**: ACID compliance, concurrent writes, pgvector support
- **Cons**: Requires PostgreSQL installation and configuration
- **Use Case**: Production, multi-agent systems

### Optimization Tips

1. **Indexes**: SQLite automatically creates indexes on key fields
2. **FTS Search**: Enable FTS only if you need full-text search
3. **Batch Operations**: Use transactions for multiple writes
4. **Vacuum Schedule**: Run vacuum during off-peak hours

## Security

### Encryption at Rest

Memory stores support encryption at rest:

```bash
# SQLite: Use encrypted filesystem or SQLite encryption extension
export MAGSAG_MEMORY_DB_PATH="/encrypted/volume/memory.db"

# PostgreSQL: Enable pgcrypto extension
# Encrypt sensitive columns: value, metadata
```

### Access Control

Memory access is controlled by agent identity:

```python
# Agents can only access their own LONG_TERM memories
memories = await store.list_memories(
    scope=MemoryScope.LONG_TERM,
    agent_slug=current_agent.slug  # Enforced by store
)

# ORG memories are accessible to all agents (read-only by default)
```

## Troubleshooting

### Memory Not Found

```python
memory = await store.get_memory(memory_id)
if memory is None:
    # Check if expired
    all_memories = await store.list_memories(include_expired=True)
    # Check memory_id spelling
    # Check if deleted by vacuum
```

### PII Tag Validation Errors

```python
# Error: Unknown PII tag 'phone_number'
# Fix: Use standard tag 'phone'
memory = create_memory(
    ...
    pii_tags=["phone"]  # Not "phone_number"
)
```

### Full-Text Search Not Working

```python
# Check if FTS is enabled
store = SQLiteMemoryStore(
    db_path="memory.db",
    enable_fts=True  # Must be True
)
```

## Future Enhancements

- **Vector Search**: Semantic search using embeddings (pgvector)
- **Memory Compression**: Automatic compression for old entries
- **Cross-Agent Sharing**: Fine-grained permissions for memory sharing
- **Versioning**: Track memory entry versions over time
- **Materialized Views**: Pre-computed aggregations for common queries

## References

- [Storage Architecture](./architecture/storage.md)
- [Governance Policies](../catalog/policies/retention_policy.yaml)
- [API Reference](./api/memory.md)
