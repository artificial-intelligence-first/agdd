# Content Moderation Guide

AGDD integrates OpenAI's omni-moderation-latest model to ensure safe content generation before and after LLM interactions.

## Overview

The moderation system provides:

- **Input moderation**: Screen user input before sending to LLM
- **Output moderation**: Validate LLM responses before returning to users
- **Multi-category detection**: Detect harassment, hate speech, violence, sexual content, self-harm, and illicit content
- **Multimodal support**: Moderate both text and image content
- **Batch processing**: Moderate multiple items efficiently

## Quick Start

### Environment Setup

```bash
# Moderation uses your OpenAI API key
export OPENAI_API_KEY="sk-..."
```

### Basic Usage

```python
from agdd.moderation import moderate_content, ModerationError

try:
    # Moderate user input
    result = moderate_content(
        "User's message here",
        check_input=True
    )

    if result.flagged:
        print(f"Content flagged: {', '.join(result.flagged_categories)}")

except ModerationError as e:
    # Content blocked due to policy violations
    print(f"Moderation failed: {e}")
    print(f"Flagged categories: {e.result.flagged_categories}")
```

## Configuration

### ModerationConfig

```python
from agdd.moderation import ModerationConfig, ModerationService

config = ModerationConfig(
    model="omni-moderation-latest",
    enable_input_moderation=True,
    enable_output_moderation=True,
    block_on_flagged=True,  # Raise error if content is flagged
    fail_closed_on_error=False,  # False: permissive on API errors, True: flag on errors
    timeout=10.0
)

service = ModerationService(config)
```

### Environment Variables

```bash
# Required
OPENAI_API_KEY="sk-..."

# Optional overrides
AGDD_MODERATION_MODEL="omni-moderation-latest"
AGDD_MODERATION_BLOCK_ON_FLAGGED="true"
AGDD_MODERATION_TIMEOUT="10.0"
```

## Integration with Agent Runner

### Automatic Moderation in Plans

Enable moderation via routing policy:

```yaml
# catalog/policies/safe_routing.yaml
name: safe-routing
description: Routing with content moderation

routes:
  - task_type: chat-completion
    provider: openai
    model: gpt-4o
    use_batch: false
    use_cache: true
    structured_output: false
    moderation: true  # Enable moderation

defaults:
  provider: openai
  model: gpt-4o-mini
  moderation: true
```

### Manual Integration in Agent Code

```python
from agdd.moderation import get_moderation_service, ModerationError

def run(payload: dict, **deps) -> dict:
    service = get_moderation_service()

    # Moderate input
    user_message = payload.get("message", "")
    try:
        input_result = service.moderate_input(user_message)
        if input_result.flagged:
            return {
                "error": "Input content violates policy",
                "flagged_categories": input_result.flagged_categories
            }
    except ModerationError as e:
        return {"error": str(e)}

    # Call LLM
    llm_response = deps['skills'].invoke("llm.completion", payload)
    output_text = llm_response.get("content", "")

    # Moderate output
    try:
        output_result = service.moderate_output(output_text)
        if output_result.flagged:
            # Regenerate or return safe fallback
            return {
                "error": "Generated content flagged",
                "flagged_categories": output_result.flagged_categories
            }
    except ModerationError as e:
        return {"error": str(e)}

    return llm_response
```

## Moderation Categories

### Standard Categories

| Category | Description |
|----------|-------------|
| `harassment` | Content that expresses, incites, or promotes harassing language |
| `harassment/threatening` | Harassment that includes threats |
| `hate` | Content that expresses, incites, or promotes hate |
| `hate/threatening` | Hate speech that includes threats |
| `illicit` | Content related to illegal activities |
| `illicit/violent` | Content promoting illegal violence |
| `self-harm` | Content promoting self-harm |
| `self-harm/intent` | Content indicating intent to self-harm |
| `self-harm/instructions` | Instructions for self-harm |
| `sexual` | Sexual content |
| `sexual/minors` | Sexual content involving minors |
| `violence` | Content depicting violence |
| `violence/graphic` | Graphic violent content |

### Analyzing Results

```python
from agdd.moderation import moderate_content

result = moderate_content("Potentially unsafe content")

# Check if flagged
if result.flagged:
    print("Content flagged!")

    # Get all flagged categories
    print(f"Flagged: {result.flagged_categories}")

    # Get highest risk category
    category, score = result.highest_risk_category
    print(f"Highest risk: {category} (score: {score:.2f})")

    # Access category scores
    for category, score in result.category_scores.items():
        if score > 0.5:
            print(f"  {category}: {score:.2%}")
```

## Advanced Features

### Multimodal Moderation

Moderate content with images:

```python
from agdd.moderation import get_moderation_service

service = get_moderation_service()

# Moderate text + image
result = service.moderate(
    content="Check this image",
    multimodal_input=[
        {
            "type": "image_url",
            "image_url": {
                "url": "https://example.com/image.jpg"
            }
        }
    ]
)

# Check which input types were flagged
for category, input_types in result.category_applied_input_types.items():
    print(f"{category}: flagged in {', '.join(input_types)}")
```

### Batch Moderation

Efficiently moderate multiple items:

```python
from agdd.moderation import get_moderation_service, ModerationConfig

service = get_moderation_service()

# Moderate list of messages
messages = [
    "First message",
    "Second message",
    "Third message"
]

results = service.batch_moderate(messages)

for msg, result in zip(messages, results):
    if result.flagged:
        print(f"Flagged: {msg[:50]}... ({result.flagged_categories})")
```

**Error Handling in Batch Mode:**

Batch moderation respects the `fail_closed_on_error` configuration:

```python
# Fail-closed: All items flagged on API error
config = ModerationConfig(fail_closed_on_error=True)
service = ModerationService(config)

results = service.batch_moderate(messages)

# If API fails, all results will have flagged=True
for i, result in enumerate(results):
    if result.metadata.get("fail_closed"):
        print(f"Item {i} flagged due to API error")

# Fail-open (default): All items permissive on API error
config = ModerationConfig(fail_closed_on_error=False)
service = ModerationService(config)

results = service.batch_moderate(messages)

# If API fails, all results will have flagged=False
for i, result in enumerate(results):
    if result.metadata.get("fallback"):
        print(f"Item {i} passed due to API error (permissive)")
```

## Cost Considerations

### Pricing

- Model: `omni-moderation-latest`
- Cost: **Free** (no charge for moderation API calls)
- Rate limits: Standard OpenAI rate limits apply

### Best Practices

1. **Cache moderation results**: For repeated content, cache results to avoid duplicate API calls
2. **Batch requests**: Use `batch_moderate()` for multiple items (single API call for multiple contents)
3. **Configure error handling**: Set `fail_closed_on_error=True` for security-critical applications
4. **Check metadata**: Always check `result.metadata` for error/fallback flags to detect API issues
5. **Async support**: For high-throughput scenarios, consider async wrappers

## Error Handling

### Error Handling Strategies

The moderation service supports two error handling strategies:

#### Fail-Open (Default, Permissive)

```python
from agdd.moderation import ModerationConfig, get_moderation_service

# Default: fail-open (permissive on errors)
config = ModerationConfig(fail_closed_on_error=False)
service = get_moderation_service(config)

# If API call fails, returns permissive result (flagged=False)
result = service.moderate("Content to check")

# Check if result is from fallback
if result.metadata.get("fallback"):
    print("Moderation API unavailable, proceeding with caution")

# Check for errors
if result.metadata.get("error"):
    print(f"Moderation error: {result.metadata['error']}")
```

#### Fail-Closed (Strict, Safer)

For security-critical applications, use fail-closed mode:

```python
# Strict: fail-closed (treat errors as policy violations)
config = ModerationConfig(fail_closed_on_error=True)
service = get_moderation_service(config)

# If API call fails, returns flagged=True
result = service.moderate("Content to check")

# Check if error caused flag
if result.metadata.get("fail_closed"):
    print(f"Content flagged due to moderation error: {result.metadata['error']}")
    # Handle as policy violation
```

**When to use fail-closed:**
- Financial services or healthcare applications
- User-generated content platforms with strict compliance requirements
- High-risk scenarios where false negatives are more costly than false positives

**When to use fail-open (default):**
- Internal tools or development environments
- Applications where false positives significantly harm UX
- Systems with fallback manual review processes

### Custom Error Handling

```python
from agdd.moderation import ModerationConfig, ModerationService

# Disable blocking to handle flags manually
config = ModerationConfig(block_on_flagged=False)
service = ModerationService(config)

result = service.moderate_input(user_message)

if result.flagged:
    # Custom logic: log, alert, or modify content
    if "violence" in result.flagged_categories:
        # Escalate to human review
        notify_moderator(user_message, result)
    elif "sexual" in result.flagged_categories:
        # Apply content filter
        filtered_message = apply_filter(user_message)
```

## Integration with Router and Plan

### Plan-Based Moderation

When `Plan.moderation=True`, agent runner applies moderation automatically:

```python
from agdd.routing import get_plan

# Get plan with moderation enabled
plan = get_plan("sensitive-content-task")

if plan and plan.moderation:
    # Moderation will be applied automatically
    # Input: before LLM call
    # Output: after LLM response
    print("Moderation enabled for this task")
```

### Observability

Moderation results are logged in observability artifacts:

```json
{
  "timestamp": "2025-01-15T10:30:00Z",
  "event_type": "moderation",
  "phase": "input",
  "flagged": false,
  "categories": {},
  "metadata": {
    "model": "omni-moderation-latest",
    "latency_ms": 120
  }
}
```

## References

- [OpenAI Moderation API](https://platform.openai.com/docs/guides/moderation)
- [Content Policy](https://openai.com/policies/usage-policies)
- [AGDD Routing Guide](./routing.md)
- [AGDD Observability](../reference/observability.md)
