# Routing Logic - YourA2AOrchestratorMAG

## A2A Communication Flow

```
External Agent/Client
    │
    ├─→ Discovery Phase
    │   └─→ GET /api/v1/agents
    │       └─→ Returns: [{slug, title, description}]
    │
    └─→ Invocation Phase
        └─→ POST /api/v1/agents/your-a2a-orchestrator-mag/run
            │
            ├─→ Phase 1: Request Validation
            │       └─→ Validate input schema
            │
            ├─→ Phase 2: Task Decomposition
            │       ├─ IF skill.task-decomposition available:
            │       │    └─→ Invoke skill → tasks[]
            │       └─ ELSE:
            │            └─→ Fallback: [default-sag]
            │
            ├─→ Phase 3: A2A Delegation
            │       └─ FOR EACH task:
            │            ├─→ Log a2a_invoke_start
            │            ├─→ Create Delegation(task_id, sag_id, input, context)
            │            ├─→ runner.invoke_sag(delegation) → Result
            │            ├─ IF status == "success":
            │            │    └─→ Collect result, log a2a_invoke_complete
            │            └─ ELSE:
            │                 └─→ Log a2a_invoke_failure, continue
            │
            ├─→ Phase 4: Result Aggregation
            │       ├─ IF skill.result-aggregation available:
            │       │    └─→ Invoke skill(results) → aggregated
            │       └─ ELSE:
            │            └─→ Fallback: Use first successful result
            │
            └─→ Phase 5: Response Formatting
                    └─→ Package with metadata and A2A trace
                        ├─ result: aggregated output
                        ├─ metadata: run stats
                        └─ trace: A2A call details
```

## SAG Selection Rules

### Current (v0.1.0)
- **Default:** Route to `your-a2a-advisor-sag`
- **Reason:** Initial A2A implementation

### Future Enhancements

#### Dynamic Agent Discovery
```python
# Discover available agents via registry
available_agents = registry.discover_agents(capability="data-processing")
# Select best agent based on criteria
selected_agent = select_best_agent(available_agents, criteria)
```

#### Load-Based Routing
```python
# Route to least loaded agent instance
if agent_load[sag_1] < agent_load[sag_2]:
    target = sag_1
else:
    target = sag_2
```

#### Capability-Based Routing
```python
# Route based on required capabilities
if "real-time-processing" in task.requirements:
    target = "real-time-sag"
elif "batch-processing" in task.requirements:
    target = "batch-sag"
```

## A2A-Specific Error Handling

### Communication Failures

```python
try:
    result = runner.invoke_sag(delegation)
except ConnectionError as e:
    # Retry with exponential backoff
    for attempt in range(max_retries):
        time.sleep(2 ** attempt)
        try:
            result = runner.invoke_sag(delegation)
            break
        except ConnectionError:
            if attempt == max_retries - 1:
                raise
```

### Timeout Handling

```python
# Set timeout for A2A calls
delegation.timeout = 10  # seconds

try:
    result = runner.invoke_sag(delegation)
except TimeoutError:
    obs.log("a2a_timeout", {"agent": sag_id, "timeout": 10})
    # Fallback to alternative agent or return partial results
```

### Circuit Breaker Pattern

```python
# Track failure rate
if failure_rate[sag_id] > 0.5:
    obs.log("circuit_breaker_open", {"agent": sag_id})
    # Route to alternative agent
    fallback_sag = get_fallback_agent(sag_id)
    result = runner.invoke_sag(fallback_sag)
```

## Context Propagation

### Standard Context
Every A2A delegation includes:
```python
context = {
    "parent_run_id": run_id,         # Current MAG run ID
    "task_index": idx,                # Position in task list
    "total_tasks": len(tasks),        # Total decomposed tasks
}
```

### A2A-Specific Context
```python
a2a_context = {
    "correlation_id": correlation_id,  # End-to-end request tracking
    "source_agent": "your-a2a-orchestrator-mag",
    "call_chain": [                    # Full agent call chain
        "external-client",
        "your-a2a-orchestrator-mag",
        "your-a2a-advisor-sag"
    ],
    "trace_id": trace_id,              # Distributed tracing ID
}
```

## Observability

### Standard Events
```jsonl
{"event":"start","agent":"YourA2AOrchestratorMAG"}
{"event":"decomposition","task_count":2}
{"event":"delegation_start","task_id":"task-1","sag_id":"your-a2a-advisor-sag"}
{"event":"delegation_complete","task_id":"task-1","status":"success"}
{"event":"aggregation","result_count":2}
{"event":"end","status":"success","duration_ms":350}
```

### A2A-Specific Events
```jsonl
{"event":"a2a_discovery","agent":"your-a2a-advisor-sag","discovered":true,"capabilities":["data-processing"]}
{"event":"a2a_invoke_start","target":"your-a2a-advisor-sag","task_id":"task-1","correlation_id":"abc-123"}
{"event":"a2a_invoke_complete","target":"your-a2a-advisor-sag","status":"success","duration_ms":150}
{"event":"a2a_invoke_failure","target":"your-a2a-advisor-sag","error":"Connection timeout","retry_attempt":1}
{"event":"a2a_circuit_breaker","agent":"failing-sag","status":"open","failure_rate":0.75}
```

### Metrics
```json
{
  "latency_ms": [{"value": 350}],
  "task_count": [{"value": 2}],
  "success_count": [{"value": 2}],
  "a2a_calls": [{"value": 3}],
  "a2a_success_rate": [{"value": 1.0}],
  "a2a_avg_latency_ms": [{"value": 120}]
}
```

## Security Considerations

### Input Validation
- Validate all incoming A2A requests against schema
- Sanitize user-provided data
- Reject malformed requests early

### Authentication (Future)
```python
# Verify calling agent identity
def verify_agent_token(token: str) -> bool:
    # Validate JWT or API key
    return is_valid_token(token)

# In orchestrator
if not verify_agent_token(request.headers.get("Authorization")):
    raise Unauthorized("Invalid agent credentials")
```

### Rate Limiting (Future)
```python
# Limit requests per agent
if request_count[source_agent] > rate_limit:
    raise RateLimitExceeded(f"Agent {source_agent} exceeded rate limit")
```

## Testing Strategies

### Unit Tests
- Test task decomposition logic
- Test result aggregation with various input combinations
- Test error handling for individual failures

### Integration Tests
- Test discovery endpoint response
- Test invocation endpoint with valid/invalid payloads
- Test A2A delegation to SAGs

### E2E Tests
- Test full discovery → invoke → aggregate → response flow
- Test multi-agent coordination scenarios
- Test failure recovery and partial result handling
