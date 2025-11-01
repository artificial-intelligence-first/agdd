# Durable Run

## Overview

Durable Run provides snapshot/restore capabilities for agent executions, enabling restart resilience and step-level idempotency. This feature ensures that long-running agent workflows can be safely interrupted and resumed without losing progress or duplicating work.

## Key Features

- **Automatic Checkpointing**: Save state at step boundaries
- **Restart Resilience**: Resume from last successful checkpoint after crashes
- **Step-Level Idempotency**: Re-executing same step updates snapshot (no duplication)
- **State Management**: Flexible JSON state storage
- **Multiple Backends**: File-based, SQLite, or PostgreSQL storage
- **Observability**: Full audit trail of checkpoints and resumes

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                 Agent Execution                             │
│                                                             │
│   Step 1 ──┬──> Checkpoint ──> Continue                    │
│            │                                                │
│   Step 2 ──┬──> Checkpoint ──> Continue                    │
│            │                                                │
│   Step 3 ──┬──> Checkpoint ──> Continue                    │
│            │                    │                           │
│            │                    ▼                           │
│            │              CRASH/RESTART                     │
│            │                    │                           │
│            │                    ▼                           │
│            │              Resume from Step 3                │
│            │                    │                           │
│            │                    ▼                           │
│   Step 4 ──┴──> Checkpoint ──> Complete                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│              Durable Runner                                 │
│   ┌─────────────────────────────────────────────────┐       │
│   │  checkpoint(run_id, step_id, state)             │       │
│   │  resume(run_id, from_step?)                     │       │
│   │  list_checkpoints(run_id)                       │       │
│   │  cleanup(run_id)                                │       │
│   └─────────────────────────────────────────────────┘       │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│           Snapshot Store                                    │
│   ┌─────────────────────────────────────────────────┐       │
│   │  save_snapshot(run_id, step_id, state)          │       │
│   │  get_latest_snapshot(run_id)                    │       │
│   │  get_snapshot_by_step(run_id, step_id)          │       │
│   │  list_snapshots(run_id)                         │       │
│   └─────────────────────────────────────────────────┘       │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│           Storage Backend                                   │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│   │ File System  │  │   SQLite     │  │  PostgreSQL  │     │
│   │ (.agdd/      │  │ (snapshots   │  │ (snapshots   │     │
│   │ snapshots/)  │  │  table)      │  │  table)      │     │
│   └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

## Usage

### Enabling Durable Run

Set the feature flag in your environment:

```bash
export AGDD_DURABLE_ENABLED=true
```

Or in your API config:

```python
from agdd.api.config import Settings

settings = Settings(
    DURABLE_ENABLED=True,
)
```

Durable snapshots emit storage events (`run.snapshot.saved`, `run.resume`) that you can stream via the storage backend for observability dashboards and replay diagnostics.

### Basic Usage

```python
from agdd.runners.durable import DurableRunner, SnapshotStore

# Initialize durable runner
snapshot_store = SnapshotStore()
durable_runner = DurableRunner(
    snapshot_store=snapshot_store,
    enable_auto_snapshot=True,
)

# Execute multi-step agent workflow
async def execute_agent_workflow(run_id: str):
    # Try to resume from previous run
    state = await durable_runner.resume(run_id)

    if state:
        # Resume from checkpoint
        print(f"Resuming from step {state.get('last_step')}")
        start_step = state.get('last_step', 0) + 1
    else:
        # Fresh start
        print("Starting new run")
        start_step = 0
        state = {"items_processed": 0, "results": []}

    # Execute steps
    steps = ["fetch_data", "process_data", "validate_results", "save_output"]

    for i in range(start_step, len(steps)):
        step_name = steps[i]

        # Execute step
        print(f"Executing step: {step_name}")
        result = await execute_step(step_name, state)

        # Update state
        state["last_step"] = i
        state["results"].append(result)

        # Checkpoint
        await durable_runner.checkpoint(
            run_id=run_id,
            step_id=step_name,
            state=state,
            metadata={"step_index": i},
        )

        print(f"Checkpointed at {step_name}")

    return state["results"]


# Execute workflow
results = await execute_agent_workflow("run-123")
```

### Checkpoint Management

```python
# Create checkpoint manually
snapshot = await durable_runner.checkpoint(
    run_id="run-123",
    step_id="step-1",
    state={
        "counter": 42,
        "processed_items": ["item1", "item2"],
        "metadata": {"timestamp": "2025-10-31T10:00:00Z"},
    },
    metadata={"agent": "my-agent"},
)

# Resume from latest checkpoint
restored_state = await durable_runner.resume("run-123")

# Resume from specific step
restored_state = await durable_runner.resume("run-123", from_step="step-1")

# List all checkpoints
checkpoints = await durable_runner.list_checkpoints("run-123")
for checkpoint in checkpoints:
    print(f"Step: {checkpoint.step_id}, Created: {checkpoint.created_at}")

# Clean up checkpoints
count = await durable_runner.cleanup("run-123")
print(f"Deleted {count} checkpoints")
```

### Integration with Agent Runner

```python
from agdd.runners.agent_runner import AgentRunner
from agdd.runners.durable import DurableRunner

class DurableAgentRunner(AgentRunner):
    """Agent runner with durable execution support."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.durable = DurableRunner()

    async def invoke_mag_durable(
        self,
        slug: str,
        payload: dict,
        run_id: str,
    ) -> dict:
        """Invoke MAG with durable checkpoints."""

        # Try to resume
        state = await self.durable.resume(run_id)

        if state:
            print(f"Resuming MAG {slug} from checkpoint")
            # Use resumed state to skip completed steps

        # Execute agent
        result = await self.invoke_mag(slug, payload)

        # Checkpoint final state
        await self.durable.checkpoint(
            run_id=run_id,
            step_id="final",
            state={"result": result},
        )

        return result
```

## Snapshot Storage

### Data Model

```python
@dataclass
class RunSnapshot:
    snapshot_id: str          # Unique snapshot identifier
    run_id: str               # Run identifier
    step_id: str              # Step identifier (for idempotency)
    created_at: datetime      # Creation timestamp
    state: Dict[str, Any]     # Execution state (JSON)
    metadata: Dict[str, Any]  # Optional metadata (JSON)
```

### Storage Backends

#### File-Based Storage (Default)

Snapshots stored in `.agdd/snapshots/{run_id}/{step_id}.json`:

```json
{
  "snapshot_id": "uuid",
  "run_id": "run-123",
  "step_id": "step-1",
  "created_at": "2025-10-31T10:00:00Z",
  "state": {
    "counter": 42,
    "items": ["a", "b", "c"]
  },
  "metadata": {
    "agent": "my-agent"
  }
}
```

#### SQLite Storage

Enable SQLite backend:

```python
from agdd.storage.backends.sqlite import SQLiteStorageBackend

storage = SQLiteStorageBackend(db_path=".agdd/storage.db")
await storage.initialize()

snapshot_store = SnapshotStore(storage_backend=storage)
```

SQLite schema:
```sql
CREATE TABLE snapshots (
    snapshot_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    state TEXT NOT NULL,  -- JSON
    metadata TEXT,        -- JSON
    UNIQUE(run_id, step_id)  -- Idempotency constraint
);

CREATE INDEX idx_snapshots_run ON snapshots(run_id);
CREATE INDEX idx_snapshots_created ON snapshots(created_at);
```

#### PostgreSQL Storage

Enable PostgreSQL backend:

```python
from agdd.storage.backends.postgres import PostgresStorageBackend

storage = PostgresStorageBackend(dsn="postgresql://user:pass@localhost/agdd")
await storage.initialize()

snapshot_store = SnapshotStore(storage_backend=storage)
```

## Step-Level Idempotency

Durable Run ensures that re-executing a step with the same `step_id` updates the snapshot rather than creating duplicates:

```python
# First execution of step-1
await durable_runner.checkpoint(
    run_id="run-123",
    step_id="step-1",
    state={"counter": 1},
)

# Re-execution of step-1 (e.g., after retry)
await durable_runner.checkpoint(
    run_id="run-123",
    step_id="step-1",
    state={"counter": 2},  # Updated state
)

# Only ONE snapshot exists for (run-123, step-1)
# State is {"counter": 2} (latest value)
```

This is enforced by the `UNIQUE(run_id, step_id)` constraint in SQLite/PostgreSQL, and by key-based deduplication in the file-based backend.

## Restart Scenarios

### Scenario 1: Graceful Shutdown

Agent saves checkpoint before shutdown:

1. Execute steps 1-3
2. Checkpoint at step 3
3. Graceful shutdown
4. Restart
5. Resume from step 3, continue with step 4

### Scenario 2: Crash/Kill

Agent crashes mid-step:

1. Execute steps 1-3 (checkpointed)
2. Start step 4 (not checkpointed)
3. **CRASH**
4. Restart
5. Resume from step 3 (last checkpoint)
6. Re-execute step 4 (should be idempotent)

### Scenario 3: Retry with Idempotency

Step fails and is retried:

1. Execute step 1 (success, checkpointed)
2. Execute step 2 (fail, no checkpoint)
3. Retry step 2 (success, checkpointed)
4. Execute step 3 (success, checkpointed)

Result: Only successful executions are checkpointed.

## Best Practices

### Checkpoint Frequency

- **Too Frequent**: Overhead from I/O operations
- **Too Rare**: Risk of losing progress
- **Recommended**: Checkpoint at logical step boundaries (every 1-10 minutes of work)

### State Management

1. **Keep State Serializable**: Use JSON-compatible types
2. **Avoid Large Objects**: Don't checkpoint large files or binary data
3. **Use References**: Store paths/IDs instead of full objects
4. **Version State Schema**: Add version field for schema evolution

Example:
```python
state = {
    "schema_version": "1.0",
    "progress": 0.75,
    "processed_ids": [1, 2, 3],
    "output_path": "/tmp/results.json",  # Reference, not full file
}
```

### Error Handling

```python
try:
    # Execute step
    result = await execute_step()

    # Checkpoint on success
    await durable_runner.checkpoint(run_id, step_id, state)

except Exception as e:
    # Don't checkpoint on failure
    logger.error(f"Step failed: {e}")
    # Raise or handle error
    raise
```

### Step Idempotency

Design steps to be idempotent (safe to re-execute):

```python
async def idempotent_step(state):
    # Check if already done
    if state.get("step_completed"):
        return state  # Skip

    # Do work
    result = await do_work()

    # Mark as completed
    state["step_completed"] = True
    state["result"] = result

    return state
```

### Cleanup

Clean up old snapshots to save storage:

```python
# Clean up after successful completion
await durable_runner.cleanup(run_id)

# Or periodically clean up old runs
async def cleanup_old_runs():
    cutoff_date = datetime.now() - timedelta(days=7)
    # Query old run IDs from storage
    for run_id in old_run_ids:
        await durable_runner.cleanup(run_id)
```

## Observability

Checkpoint events are logged for observability:

```json
{
  "event_type": "checkpoint.saved",
  "run_id": "run-123",
  "step_id": "step-1",
  "snapshot_id": "uuid",
  "state_size_bytes": 1024,
  "created_at": "2025-10-31T10:00:00Z"
}
```

Resume events:
```json
{
  "event_type": "checkpoint.restored",
  "run_id": "run-123",
  "step_id": "step-3",
  "snapshot_id": "uuid",
  "restored_at": "2025-10-31T11:00:00Z"
}
```

## Performance Considerations

### Write Overhead

Checkpointing adds I/O overhead:

- **File-based**: ~1-10ms per checkpoint (depends on state size)
- **SQLite**: ~5-20ms per checkpoint (includes transaction)
- **PostgreSQL**: ~10-50ms per checkpoint (network + transaction)

**Mitigation**: Checkpoint at coarse-grained boundaries, not every operation.

### State Size

Large states increase checkpoint time and storage:

- **Recommended**: < 1MB per checkpoint
- **Acceptable**: 1-10MB per checkpoint
- **Problematic**: > 10MB per checkpoint

**Mitigation**: Store references instead of full objects.

### Storage Growth

Checkpoints accumulate over time:

- **Estimate**: ~100 KB per checkpoint × 10 checkpoints/run × 1000 runs = ~1 GB
- **Mitigation**: Implement retention policy and periodic cleanup

## Limitations

1. **No Automatic Rollback**: Durable Run provides resume, not rollback
2. **Step Granularity**: Checkpoints only at explicit step boundaries
3. **State Serializability**: State must be JSON-serializable
4. **No Cross-Run Dependencies**: Each run is independent

## Future Enhancements

- **Automatic Retry**: Retry failed steps with exponential backoff
- **Partial Rollback**: Rollback to previous checkpoint on error
- **Snapshot Compression**: Compress large states
- **Snapshot Encryption**: Encrypt sensitive state data
- **Distributed Snapshots**: Coordinate snapshots across multiple agents

## Related Documentation

- [Storage Layer](./storage.md)
- [Agent Runner](./guides/runner-integration.md)
- [Observability](./guides/cost-optimization.md)
- [API Usage](./guides/api-usage.md)
