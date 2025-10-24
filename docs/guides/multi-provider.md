# Multi-Provider LLM Support

AGDD supports multiple LLM providers through flexible configuration and runtime model selection. This guide covers provider integration, model selection strategies, and best practices.

## Overview

The AGDD framework tracks model usage across different providers through observability instrumentation, enabling:

- **Provider diversity**: Use multiple LLM providers (OpenAI, Anthropic, local models) within the same workflow
- **Fallback strategies**: Automatic failover when primary provider is unavailable
- **Cost optimization**: Route tasks to cost-effective models based on requirements
- **Performance tuning**: Select models based on latency, throughput, and accuracy needs

## Provider Configuration

### Environment Variables

Configure provider credentials via environment variables:

```bash
# OpenAI
export OPENAI_API_KEY="sk-..."
export OPENAI_BASE_URL="https://api.openai.com/v1"  # optional

# Anthropic
export ANTHROPIC_API_KEY="sk-ant-..."

# Azure OpenAI
export AZURE_OPENAI_API_KEY="..."
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"

# Local providers (Ollama, LM Studio)
export OLLAMA_BASE_URL="http://localhost:11434"
```

AGDD's local provider (`src/agdd/providers/local.py`) prefers the OpenAI Responses API. If the endpoint rejects Responses or returns a legacy status code, the provider automatically falls back to chat completions while recording a warning in the response metadata.

### Model Selection in Agent Code

Agents specify model preferences by including them in the payload or context:

```python
# In your MAG or SAG code
def run(payload: dict, *, registry=None, skills=None, runner=None, obs=None) -> dict:
    # Option 1: Include model preference in payload
    analysis_payload = {
        **payload,
        "model_config": {
            "model": "gpt-4o",
            "provider": "openai"
        }
    }
    result = skills.invoke("skill.analysis", analysis_payload)

    # Option 2: Delegate to SAG with model preference in context
    delegation = Delegation(
        task_id="analyze-1",
        sag_id="data-analysis-sag",
        input=payload,
        context={"preferred_model": "claude-3-5-sonnet-20241022"}
    )
    result = runner.invoke_sag(delegation)

    return result
```

## Model Selection Strategies

### Strategy 1: Task-Based Routing

Route different task types to appropriate models:

```python
MODEL_ROUTING = {
    "reasoning": "o1-preview",              # Complex reasoning tasks
    "coding": "claude-3-5-sonnet-20241022", # Code generation
    "analysis": "gpt-4o",                   # Data analysis
    "summarization": "gpt-4o-mini",         # Fast summaries
    "local": "llama3.1:70b"                 # Local inference
}

def select_model(task_type: str) -> str:
    return MODEL_ROUTING.get(task_type, "gpt-4o")

# Use in agent code
def run(payload: dict, **deps) -> dict:
    task_type = payload.get("task_type", "analysis")
    model = select_model(task_type)

    analysis_payload = {**payload, "model_config": {"model": model}}
    return deps['skills'].invoke("skill.analysis", analysis_payload)
```

### Strategy 2: Cost-Based Selection

Choose models based on budget constraints:

```python
COST_TIERS = {
    "premium": ["o1-preview", "gpt-4o"],
    "standard": ["claude-3-5-sonnet-20241022", "gpt-4o"],
    "economy": ["gpt-4o-mini", "claude-3-haiku-20240307"]
}

def select_by_budget(budget_tier: str) -> str:
    models = COST_TIERS.get(budget_tier, COST_TIERS["standard"])
    return models[0]  # Return primary model for tier
```

### Strategy 3: Fallback Cascade

Implement automatic fallback when primary model fails:

```python
FALLBACK_CHAIN = [
    "claude-3-5-sonnet-20241022",  # Primary
    "gpt-4o",                       # Fallback 1
    "gpt-4o-mini"                   # Fallback 2 (last resort)
]

def invoke_with_fallback(skill_id: str, payload: dict, skills, obs) -> dict:
    last_error = None

    for model in FALLBACK_CHAIN:
        try:
            # Include model in payload
            model_payload = {**payload, "model_config": {"model": model}}
            result = skills.invoke(skill_id, model_payload)
            if obs:
                obs.log("model_success", {"model": model, "skill": skill_id})
            return result
        except Exception as e:
            last_error = e
            if obs:
                obs.log("model_failed", {"model": model, "error": str(e)})
            continue

    raise RuntimeError(f"All models failed: {last_error}")
```

## Observability and Tracking

### Model Usage Metrics

The observability layer automatically tracks model usage:

```python
# Metrics collected per model:
# - calls: Number of invocations
# - errors: Failed calls
# - input_tokens: Total input tokens
# - output_tokens: Total output tokens
# - cost_usd: Total cost in USD
```

### Query Model Statistics

```bash
# View model usage in run summary
uv run agdd flow summarize --output summary.json
cat summary.json | jq '.model_stats'

# Example output:
{
  "gpt-4o": {
    "calls": 15,
    "errors": 0,
    "input_tokens": 45230,
    "output_tokens": 8940,
    "total_tokens": 54170,
    "cost_usd": 1.45
  },
  "claude-3-5-sonnet-20241022": {
    "calls": 8,
    "errors": 1,
    "input_tokens": 32100,
    "output_tokens": 12400,
    "total_tokens": 44500,
    "cost_usd": 2.18
  }
}
```

### Storage Layer Queries

```bash
# Query runs by model usage
uv run agdd data query --agent my-mag --limit 20

# Search for specific model errors
uv run agdd data search "claude.*error" --limit 50
```

## Best Practices

### 1. Model Selection Guidelines

| Use Case | Recommended Model | Rationale |
|----------|------------------|-----------|
| Complex reasoning | o1-preview | Advanced reasoning capabilities |
| Code generation | claude-3-5-sonnet-20241022 | Superior code quality |
| Data analysis | gpt-4o | Balanced performance/cost |
| Rapid prototyping | gpt-4o-mini | Fast iteration, low cost |
| High-volume tasks | gpt-4o-mini | Cost-effective scaling |
| Local/private | llama3.1:70b | No API dependency |

### 2. Error Handling

Always implement graceful degradation:

```python
def robust_invoke(skill_id: str, payload: dict, skills, obs) -> dict:
    try:
        # Try premium model first
        gpt4_payload = {**payload, "model_config": {"model": "gpt-4o"}}
        return skills.invoke(skill_id, gpt4_payload)
    except RateLimitError:
        if obs:
            obs.log("rate_limit", {"model": "gpt-4o"})
        # Fall back to alternative provider
        claude_payload = {**payload, "model_config": {"model": "claude-3-5-sonnet-20241022"}}
        return skills.invoke(skill_id, claude_payload)
    except Exception as e:
        if obs:
            obs.log("error", {"model": "gpt-4o", "error": str(e)})
        raise
```

### 3. Cost Management

Track and limit costs in production:

```python
def check_budget(obs, max_cost_usd: float = 10.0):
    """Check if run is within budget constraints"""
    # This would integrate with observability metrics
    current_cost = obs.get_current_cost()
    if current_cost > max_cost_usd:
        raise RuntimeError(f"Budget exceeded: ${current_cost:.2f} > ${max_cost_usd:.2f}")
```

### 4. Rate Limit Handling

Implement exponential backoff for rate limits:

```python
import time

def invoke_with_retry(skill_id: str, payload: dict, skills, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            return skills.invoke(skill_id, payload)
        except RateLimitError:
            if attempt == max_retries - 1:
                raise
            wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
            time.sleep(wait_time)
```

## Provider-Specific Features

### OpenAI

```python
# Function calling
analysis_payload = {
    **payload,
    "model_config": {
        "model": "gpt-4o",
        "tools": [{"type": "function", "function": {...}}]
    }
}
result = skills.invoke("skill.analysis", analysis_payload)

# JSON mode
extraction_payload = {
    **payload,
    "model_config": {
        "model": "gpt-4o",
        "response_format": {"type": "json_object"}
    }
}
result = skills.invoke("skill.extraction", extraction_payload)
```

### Anthropic

```python
# Extended context (200K tokens)
doc_payload = {
    **payload,
    "model_config": {
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 4096
    }
}
result = skills.invoke("skill.document-analysis", doc_payload)

# System prompts (separate from user content)
assistant_payload = {
    **payload,
    "model_config": {
        "model": "claude-3-5-sonnet-20241022",
        "system": "You are a helpful coding assistant..."
    }
}
result = skills.invoke("skill.assistant", assistant_payload)
```

### Local Models (Ollama)

```python
# Use local models for privacy-sensitive tasks
pii_payload = {
    **payload,
    "model_config": {
        "model": "llama3.1:70b",
        "base_url": "http://localhost:11434"
    }
}
result = skills.invoke("skill.pii-redaction", pii_payload)
```

## Governance and Compliance

### Policy Enforcement

Define provider policies in `catalog/policies/model_governance.yaml`:

```yaml
policies:
  - name: production_models
    description: Allowed models in production
    allowed_models:
      - gpt-4o
      - gpt-4o-mini
      - claude-3-5-sonnet-20241022

  - name: cost_limits
    description: Maximum cost per run
    thresholds:
      max_cost_per_run_usd: 5.0
      max_cost_per_agent_daily_usd: 100.0

  - name: data_residency
    description: Models for sensitive data
    requirements:
      pii_processing: ["llama3.1:70b"]  # Local only
      financial_data: ["gpt-4o"]  # Approved providers
```

### Audit Trail

All model invocations are logged for compliance:

```bash
# Query model usage audit trail
uv run agdd data query --run-id mag-abc123

# Export for compliance review
uv run agdd data query --agent sensitive-data-mag --format csv > audit.csv
```

## Migration Guide

### From Single Provider

If you're currently using a single provider, migrate gradually:

1. **Add observability**: Ensure model tracking is enabled
2. **Test alternatives**: Run A/B tests with different models
3. **Implement fallbacks**: Add secondary providers for resilience
4. **Monitor costs**: Track spending across providers
5. **Update policies**: Define model selection rules

### Example Migration

```python
# Before (single provider)
def run(payload: dict, **deps) -> dict:
    return deps['skills'].invoke("skill.analysis", payload)

# After (multi-provider with fallback)
def run(payload: dict, **deps) -> dict:
    skills, obs = deps['skills'], deps['obs']

    # Try primary model
    try:
        gpt4_payload = {**payload, "model_config": {"model": "gpt-4o"}}
        result = skills.invoke("skill.analysis", gpt4_payload)
        obs.log("model_used", {"model": "gpt-4o"})
        return result
    except Exception as e:
        obs.log("fallback", {"from": "gpt-4o", "to": "claude-3-5-sonnet-20241022", "reason": str(e)})
        claude_payload = {**payload, "model_config": {"model": "claude-3-5-sonnet-20241022"}}
        return skills.invoke("skill.analysis", claude_payload)
```

## Troubleshooting

### Provider Authentication Errors

```bash
# Verify credentials
echo $OPENAI_API_KEY | wc -c  # Should be ~50+ chars
echo $ANTHROPIC_API_KEY | wc -c  # Should be ~100+ chars

# Test provider connectivity
curl -H "Authorization: Bearer $OPENAI_API_KEY" https://api.openai.com/v1/models
```

### Rate Limit Issues

Monitor rate limit headers and implement backoff:

```python
# Check observability logs for rate limit errors
uv run agdd data search "rate_limit" --limit 100

# Implement request throttling in high-volume scenarios
```

### Cost Overruns

```bash
# Monitor daily costs
uv run agdd flow summarize | jq '.model_stats[].cost_usd' | awk '{s+=$1} END {print s}'

# Set up alerts in governance policies
uv run agdd flow gate summary.json --policy catalog/policies/model_governance.yaml
```

## Related Documentation

- [Cost Optimization Guide](./cost-optimization.md) - Strategies for minimizing LLM costs
- [Agent Development Guide](./agent-development.md) - Building MAG/SAG agents
- [MCP Integration Guide](./mcp-integration.md) - Model Context Protocol usage
- [Storage Layer](../storage.md) - Querying model usage data

## References

- [OpenAI Platform Docs](https://platform.openai.com/docs)
- [Anthropic API Reference](https://docs.anthropic.com/claude/reference)
- [Ollama Documentation](https://ollama.ai/docs)
- [Azure OpenAI Service](https://learn.microsoft.com/en-us/azure/ai-services/openai/)
