---
title: Cost Optimization Guide
last_synced: 2025-10-24
description: Strategies for optimizing LLM costs through model selection, token management, and usage tracking
change_log:
  - 2025-10-24: Added front-matter and cost tracking architecture
---

# Cost Optimization Guide

This guide covers strategies and best practices for optimizing LLM costs in the AGDD framework, from model selection to token management and usage tracking.

## Overview

The AGDD framework provides comprehensive cost tracking and optimization capabilities:

- **Token usage monitoring**: Track input/output tokens per model and agent
- **Cost attribution**: Calculate costs per run, agent, and model
- **Budget enforcement**: Set spending limits and governance policies
- **Optimization strategies**: Reduce costs through model selection and prompt engineering

## Cost Tracking Architecture

### Automatic Cost Calculation

AGDD automatically tracks costs for all LLM invocations:

```python
# Cost data structure (per model)
{
  "model": "gpt-4o",
  "calls": 15,
  "input_tokens": 45230,
  "output_tokens": 8940,
  "total_tokens": 54170,
  "cost_usd": 1.45  # Automatically calculated
}
```

### Cost Calculation Formula

Costs are calculated based on current provider pricing:

```python
# OpenAI GPT-4o example
INPUT_COST_PER_1M = 2.50   # $2.50 per 1M input tokens
OUTPUT_COST_PER_1M = 10.00 # $10.00 per 1M output tokens

cost_usd = (
    (input_tokens / 1_000_000 * INPUT_COST_PER_1M) +
    (output_tokens / 1_000_000 * OUTPUT_COST_PER_1M)
)
```

### Observability Integration

Cost data is captured in multiple observability artifacts:

```bash
# Run summaries
.runs/agents/<RUN_ID>/summary.json

# MCP call logs
.runs/agents/<RUN_ID>/mcp_calls.jsonl

# Cost ledger (append-only)
.runs/costs/costs.jsonl

# Aggregated SQLite database
.runs/costs.db

# Storage layer (queryable)
uv run agdd data query --run-id <RUN_ID>
```

The JSONL ledger and SQLite database are maintained by `agdd.observability.cost_tracker` and initialize automatically on first use.

## Viewing Cost Data

### CLI Commands

```bash
# Summarize costs for recent runs
uv run agdd flow summarize --output summary.json
cat summary.json | jq '.model_stats'

# Query specific run costs
uv run agdd data query --run-id mag-abc123

# Query runs by agent
uv run agdd data query --agent my-mag --limit 100

# Search for cost-related events
uv run agdd data search "cost_usd" --limit 50
```

### Programmatic Access

```python
from agdd.storage import get_storage_backend

async def calculate_daily_cost(agent_slug: str) -> float:
    storage = await get_storage_backend()

    # Query recent runs for the agent
    runs = await storage.list_runs(agent_slug=agent_slug, limit=1000)

    total_cost = 0.0
    for run in runs:
        # Filter runs from last 24 hours
        run_age_hours = (datetime.now() - run.start_time).total_seconds() / 3600
        if run_age_hours > 24:
            continue

        events = await storage.get_events(run.run_id, event_type="metric")
        async for event in events:
            if "cost_usd" in event.payload:
                total_cost += event.payload["cost_usd"]

    await storage.close()
    return total_cost
```

## Cost Optimization Strategies

### 1. Semantic Caching

Reduce costs by caching similar queries using vector similarity search:

```python
from agdd.optimization.cache import create_cache, CacheConfig

# Enable semantic cache
config = CacheConfig(backend="faiss", dimension=768)
cache = create_cache(config)

# 95% threshold = high precision, fewer false hits
matches = cache.search(query_embedding, k=1, threshold=0.95)
if matches:
    # Cache hit - no LLM call needed
    return matches[0].value
```

**Cost Impact:** 100% savings on cache hits (no LLM call)

**See:** [Semantic Cache Guide](./semantic-cache.md) for implementation details

### 2. Batch API (50% Discount)

For non-realtime workloads, use OpenAI Batch API:

```python
from agdd.optimization.batch import BatchAPIClient, BatchRequest

client = BatchAPIClient()

# Create batch requests
requests = [
    BatchRequest(
        custom_id=f"req-{i}",
        url="/v1/responses",
        body={"model": "gpt-4o", "input": [...]}
    )
    for i in range(100)
]

# Submit batch (50% cost reduction, 24h completion)
batch = client.submit_batch(requests)
```

**Cost Impact:** 50% reduction on all batched requests

**See:** `src/agdd/optimization/batch.py` for implementation

### 3. Model Selection

Choose the right model for each task:

| Task Type | High-Cost Model | Optimized Alternative | Savings |
|-----------|----------------|----------------------|---------|
| Simple classification | gpt-4o ($2.50/$10) | gpt-4o-mini ($0.15/$0.60) | ~94% |
| Summarization | claude-3-opus | claude-3-haiku | ~90% |
| Code review | o1-preview | gpt-4o | ~75% |
| Data extraction | gpt-4o | gpt-4o-mini | ~94% |
| Complex reasoning | o1-preview | Keep premium | - |

**Implementation:**

```python
# Task-based model routing
TASK_MODEL_MAP = {
    "classification": "gpt-4o-mini",
    "extraction": "gpt-4o-mini",
    "summarization": "claude-3-haiku-20240307",
    "reasoning": "o1-preview",
    "coding": "claude-3-5-sonnet-20241022"
}

def select_optimal_model(task_type: str) -> str:
    return TASK_MODEL_MAP.get(task_type, "gpt-4o-mini")  # Default to cheap
```

### 4. Prompt Engineering

Reduce token usage through efficient prompts:

**Before (verbose):**
```python
prompt = f"""
Please analyze the following candidate profile and provide a detailed
comprehensive assessment of their qualifications, experience, and fit
for the role. Consider all aspects including technical skills, soft
skills, years of experience, education, and any other relevant factors.

Candidate Profile:
{json.dumps(profile, indent=2)}

Please structure your response with clear sections and provide actionable
recommendations for the hiring manager.
"""
# ~150 tokens
```

**After (concise):**
```python
prompt = f"""Assess candidate fit for role. Profile: {json.dumps(profile)}
Return: skills_match (0-100), experience_fit (0-100), recommendations."""
# ~40 tokens - 73% reduction
```

### 5. Response Length Control

Limit output tokens for cost-sensitive tasks:

```python
# Without limits
result = skills.invoke("skill.analysis", payload)
# May generate 2000+ tokens

# With limits
result = skills.invoke(
    "skill.analysis",
    payload,
    max_tokens=500  # Cap output at 500 tokens
)
# Saves ~75% on output costs
```

### 4. Caching and Deduplication

Avoid redundant LLM calls:

```python
from functools import lru_cache
import hashlib
import json

@lru_cache(maxsize=1000)
def invoke_with_cache(skill_id: str, payload_hash: str, payload: dict, skills):
    """Cache skill invocations based on input hash"""
    return skills.invoke(skill_id, payload)

def cached_invoke(skill_id: str, payload: dict, skills):
    # Create stable hash of input
    payload_str = json.dumps(payload, sort_keys=True)
    payload_hash = hashlib.sha256(payload_str.encode()).hexdigest()

    return invoke_with_cache(skill_id, payload_hash, json.dumps(payload), skills)
```

### 5. Batch Processing

Process multiple items in a single call:

```python
# Inefficient: N calls
for item in items:
    result = skills.invoke("skill.classify", {"item": item})
    # Cost: N * base_cost

# Efficient: 1 call
batch_payload = {"items": items}
results = skills.invoke("skill.classify-batch", batch_payload)
# Cost: base_cost + marginal_token_cost
# Savings: ~60-80%
```

### 6. Streaming for Early Termination

Use streaming to stop generation early:

```python
def invoke_with_early_stop(skill_id: str, payload: dict, skills, stop_condition):
    """Stream response and stop when condition is met"""
    accumulated = ""

    for chunk in skills.invoke_stream(skill_id, payload):
        accumulated += chunk
        if stop_condition(accumulated):
            # Stop generation early, save output tokens
            return accumulated

    return accumulated

# Example: Stop after finding answer
result = invoke_with_early_stop(
    "skill.search",
    payload,
    skills,
    stop_condition=lambda text: "Answer:" in text and "\n\n" in text.split("Answer:")[1]
)
```

### 7. Model Cascading

Try cheap models first, escalate if needed:

```python
def cascading_invoke(skill_id: str, payload: dict, skills, obs):
    """Try cheap model first, escalate if quality is insufficient"""

    # Tier 1: Cheap and fast
    try:
        result = skills.invoke(skill_id, payload, model="gpt-4o-mini")
        quality_score = assess_quality(result)

        if quality_score >= 0.8:  # Good enough
            obs.log("tier1_success", {"cost_tier": "economy"})
            return result
    except Exception as e:
        obs.log("tier1_failed", {"error": str(e)})

    # Tier 2: Premium model for complex cases
    obs.log("escalating", {"from": "gpt-4o-mini", "to": "gpt-4o"})
    return skills.invoke(skill_id, payload, model="gpt-4o")

def assess_quality(result: dict) -> float:
    """Simple quality heuristic"""
    # Check for incomplete responses, errors, etc.
    if not result or "error" in result:
        return 0.0
    if len(str(result)) < 50:  # Too short
        return 0.5
    return 1.0  # Assume good quality
```

## Budget Management

### Setting Budget Limits

Define budget policies in `catalog/policies/cost_governance.yaml`:

```yaml
policies:
  - name: agent_budget_limits
    description: Maximum spending per agent
    limits:
      offer-orchestrator-mag:
        max_cost_per_run_usd: 2.0
        max_cost_per_day_usd: 50.0
        max_cost_per_month_usd: 1000.0

      compensation-advisor-sag:
        max_cost_per_run_usd: 0.5
        max_cost_per_day_usd: 20.0

  - name: model_budget_limits
    description: Maximum spending per model
    limits:
      o1-preview:
        max_daily_spend_usd: 100.0
        require_approval: true

      gpt-4o:
        max_daily_spend_usd: 200.0

  - name: cost_alerts
    description: Alert thresholds
    thresholds:
      warn_cost_per_run_usd: 1.0
      error_cost_per_run_usd: 5.0
```

### Enforcing Budgets

```python
class BudgetGuard:
    def __init__(self, max_cost_usd: float, obs):
        self.max_cost_usd = max_cost_usd
        self.obs = obs
        self.current_cost = 0.0

    def check_and_update(self, call_cost: float):
        """Check budget before allowing LLM call"""
        projected_cost = self.current_cost + call_cost

        if projected_cost > self.max_cost_usd:
            self.obs.log("budget_exceeded", {
                "current": self.current_cost,
                "projected": projected_cost,
                "limit": self.max_cost_usd
            })
            raise BudgetExceededError(
                f"Budget exceeded: ${projected_cost:.2f} > ${self.max_cost_usd:.2f}"
            )

        self.current_cost += call_cost

# Usage in agent code
def run(payload: dict, **deps) -> dict:
    budget = BudgetGuard(max_cost_usd=2.0, obs=deps['obs'])

    # Before each expensive call
    estimated_cost = estimate_call_cost(payload)
    budget.check_and_update(estimated_cost)

    result = deps['skills'].invoke("skill.analysis", payload)
    return result
```

### Cost Governance Gate

```bash
# Gate on cost thresholds
uv run agdd flow gate summary.json \
  --policy catalog/policies/cost_governance.yaml

# Fail CI if costs exceed limits
if [ $? -ne 0 ]; then
  echo "Cost governance check failed"
  exit 1
fi
```

## Cost Attribution and Chargeback

### Per-Agent Cost Tracking

```bash
# Generate cost report by agent
uv run python ops/scripts/cost_report.py --agent offer-orchestrator-mag

# Output:
# Agent: offer-orchestrator-mag
# Period: 2024-01-01 to 2024-01-31
# Total Runs: 1,234
# Total Cost: $145.67
# Avg Cost per Run: $0.118
# Models Used:
#   - gpt-4o: $98.23 (67%)
#   - gpt-4o-mini: $47.44 (33%)
```

### Per-Customer Cost Allocation

Track costs by customer/tenant:

```python
# Include customer ID in context
delegation = Delegation(
    task_id="task-1",
    sag_id="compensation-advisor-sag",
    input=payload,
    context={
        "customer_id": "acme-corp",
        "billing_tier": "enterprise"
    }
)

# Query costs by customer
async def get_customer_cost(customer_id: str, month: str) -> float:
    storage = await get_storage_backend()

    # Filter events by customer context
    runs = await storage.list_runs(limit=10000)
    total_cost = 0.0

    for run in runs:
        if run.context.get("customer_id") == customer_id:
            events = await storage.get_events(run.run_id, event_type="metric")
            async for event in events:
                if "cost_usd" in event.payload:
                    total_cost += event.payload["cost_usd"]

    await storage.close()
    return total_cost
```

## Cost Monitoring and Alerts

### Real-Time Monitoring

```python
# Monitor costs during execution
class CostMonitor:
    def __init__(self, alert_threshold_usd: float = 1.0):
        self.alert_threshold = alert_threshold_usd
        self.total_cost = 0.0

    def record_call(self, cost_usd: float, model: str, obs):
        self.total_cost += cost_usd

        obs.log("cost_update", {
            "model": model,
            "call_cost": cost_usd,
            "total_cost": self.total_cost
        })

        if self.total_cost > self.alert_threshold:
            obs.log("cost_alert", {
                "total_cost": self.total_cost,
                "threshold": self.alert_threshold
            })
```

### Daily Cost Reports

```bash
#!/bin/bash
# ops/scripts/daily_cost_report.sh

DATE=$(date +%Y-%m-%d)
REPORT_FILE="reports/costs_${DATE}.json"

# Generate daily summary
uv run python -c "
import asyncio
import json
from datetime import datetime, timedelta
from agdd.storage import get_storage_backend

async def daily_report():
    storage = await get_storage_backend()
    # Query recent runs (note: no time filter, so we filter in code)
    runs = await storage.list_runs(limit=10000)

    costs_by_agent = {}
    cutoff = datetime.now() - timedelta(days=1)

    for run in runs:
        # Skip old runs
        if run.start_time < cutoff:
            continue

        agent = run.agent_slug
        if agent not in costs_by_agent:
            costs_by_agent[agent] = 0.0

        events = storage.get_events(run.run_id, event_type='metric')
        async for event in events:
            if 'cost_usd' in event.payload:
                costs_by_agent[agent] += event.payload['cost_usd']

    print(json.dumps(costs_by_agent, indent=2))
    await storage.close()

asyncio.run(daily_report())
" > "$REPORT_FILE"

# Alert if total exceeds threshold
TOTAL=$(cat "$REPORT_FILE" | jq '[.[] | values] | add')
if (( $(echo "$TOTAL > 100.0" | bc -l) )); then
  echo "ALERT: Daily cost exceeded \$100: \$TOTAL"
  # Send notification (email, Slack, PagerDuty, etc.)
fi
```

## Cost Benchmarking

### Measure Cost Efficiency

```python
def calculate_cost_efficiency(run_id: str) -> dict:
    """Calculate cost efficiency metrics for a run"""
    summary = load_run_summary(run_id)

    return {
        "cost_per_successful_task": (
            summary["total_cost_usd"] / summary["successful_tasks"]
            if summary["successful_tasks"] > 0 else float('inf')
        ),
        "cost_per_1k_tokens": (
            summary["total_cost_usd"] / (summary["total_tokens"] / 1000)
            if summary["total_tokens"] > 0 else float('inf')
        ),
        "token_efficiency": (
            summary["output_tokens"] / summary["input_tokens"]
            if summary["input_tokens"] > 0 else 0
        )
    }
```

### A/B Testing for Cost Optimization

```python
def ab_test_models(skill_id: str, payload: dict, skills, obs):
    """Run A/B test between cheap and expensive models"""
    import random

    variant = random.choice(["cheap", "expensive"])

    if variant == "cheap":
        model = "gpt-4o-mini"
        expected_cost = 0.01  # ~$0.01 per call
    else:
        model = "gpt-4o"
        expected_cost = 0.05  # ~$0.05 per call

    obs.log("ab_test", {"variant": variant, "model": model})

    start = time.time()
    result = skills.invoke(skill_id, payload, model=model)
    duration = time.time() - start

    obs.log("ab_result", {
        "variant": variant,
        "model": model,
        "duration_ms": duration * 1000,
        "cost_usd": expected_cost,
        "quality_score": assess_quality(result)
    })

    return result
```

## Best Practices

### 1. Start with Cheap Models

Default to cost-effective models and escalate only when necessary:

```python
DEFAULT_MODEL = "gpt-4o-mini"  # Cheap default
PREMIUM_MODEL = "gpt-4o"       # Escalate when needed
```

### 2. Implement Token Budgets

Set token limits to prevent runaway costs:

```python
MAX_INPUT_TOKENS = 4000
MAX_OUTPUT_TOKENS = 1000

result = skills.invoke(
    "skill.analysis",
    truncate_input(payload, MAX_INPUT_TOKENS),
    max_tokens=MAX_OUTPUT_TOKENS
)
```

### 3. Monitor Cost Trends

Track cost trends over time:

```bash
# Analyze cost trends from run summaries
# Note: Requires custom script to aggregate costs over time windows
python ops/scripts/analyze_cost_trends.py --weeks 4

# Or manually review recent run costs
for agent in offer-orchestrator-mag compensation-advisor-sag; do
  echo "Agent: $agent"
  uv run agdd data query --agent "$agent" --limit 100 | \
    jq -r '.[] | "\(.run_id): \(.total_cost_usd // 0)"'
done
```

### 4. Educate Agent Developers

Provide cost awareness training:

- **Token cost basics**: Input vs output pricing
- **Model selection**: When to use cheap vs expensive models
- **Prompt engineering**: Techniques to reduce token usage
- **Testing**: Always test cost before production deployment

### 5. Automate Cost Optimization

Use CI/CD to catch cost regressions:

```yaml
# .github/workflows/cost-check.yml
name: Cost Regression Check

on: [pull_request]

jobs:
  cost-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run test suite
        run: uv run -m pytest
      - name: Generate cost summary
        run: uv run agdd flow summarize --output summary.json
      - name: Check cost governance
        run: |
          uv run agdd flow gate summary.json \
            --policy catalog/policies/cost_governance.yaml
      - name: Compare with baseline
        run: |
          CURRENT_COST=$(cat summary.json | jq '.total_cost_usd')
          BASELINE_COST=$(cat baseline_summary.json | jq '.total_cost_usd')
          INCREASE=$(echo "($CURRENT_COST - $BASELINE_COST) / $BASELINE_COST * 100" | bc -l)
          if (( $(echo "$INCREASE > 20" | bc -l) )); then
            echo "Cost increased by ${INCREASE}% - regression detected"
            exit 1
          fi
```

## Troubleshooting

### Unexpected High Costs

```bash
# Query recent runs to find expensive ones
uv run agdd data query --limit 100

# Search for cost metrics
uv run agdd data search "cost_usd" --limit 100

# Analyze specific agent's cost patterns
uv run agdd data query --agent my-mag --limit 50

# Use custom script for detailed analysis
uv run python ops/scripts/analyze_token_usage.py --agent my-mag
```

### Budget Exceeded Errors

```bash
# Review recent spending
uv run agdd data query --agent my-mag --limit 50

# Analyze cost trends in summaries
uv run agdd flow summarize --output summary.json
cat summary.json | jq '.model_stats'

# Adjust budget limits
vim catalog/policies/cost_governance.yaml

# Test with dry-run
uv run agdd flow gate summary.json --dry-run
```

## Related Documentation

- [Multi-Provider Guide](./multi-provider.md) - Multiple LLM provider support
- [Agent Development Guide](./agent-development.md) - Building cost-aware agents
- [Storage Layer](../storage.md) - Querying cost data
- [Governance](../architecture/ssot.md) - Policy enforcement

## References

- [OpenAI Pricing](https://openai.com/pricing)
- [Anthropic Pricing](https://www.anthropic.com/pricing)
- [Token Optimization Best Practices](https://platform.openai.com/docs/guides/optimization)
- [Prompt Engineering Guide](https://www.promptingguide.ai/)
