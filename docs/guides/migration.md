---
title: MAGSAG Migration Guide
last_synced: 2025-10-30
description: "Guide for migrating from legacy features to current MAGSAG implementation."
---

# MAGSAG Migration Guide

This guide helps you migrate from legacy features to the current implementation.

## Breaking Changes Summary

As of October 2025, MAGSAG has made significant simplifications:
- **All skills must be async** - Synchronous skills are no longer supported
- **All agents must be async** - Synchronous agents are no longer supported  
- **Google SDK consolidated** - Only `google-genai` SDK is supported
- **Documentation consolidated** - Single source of truth is now [SSOT.md](../architecture/ssot.md)

## Migrating from Synchronous to Asynchronous Skills

### Before (Synchronous - No longer supported)
```python
from magsag.skills.base import Skill

class MySkill:
    def __call__(self, text: str) -> str:
        result = process_text(text)
        return result
```

### After (Asynchronous - Required)
```python
from magsag.skills.base import MCPSkill
from typing import Any, Dict

class MySkill:
    async def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Convert string input to dict if needed
        if isinstance(payload, str):
            payload = {"text": payload}
        
        result = await async_process_text(payload["text"])
        return {"result": result}
```

### Key Changes:
1. Change `def __call__` to `async def execute`
2. Change input from `str` to `Dict[str, Any]`
3. Change output from `str` to `Dict[str, Any]`
4. Use `await` for any I/O operations

## Migrating from Synchronous to Asynchronous Agents

### Before (Synchronous - No longer supported)
```python
def my_agent(payload, registry=None, skills=None, obs=None):
    result = skills.invoke("my-skill", {"input": payload})
    return {"output": result}
```

### After (Asynchronous - Required)
```python
async def my_agent(payload, registry=None, skills=None, obs=None, runner=None):
    result = await skills.invoke_async("my-skill", {"input": payload})
    return {"output": result}
```

### Key Changes:
1. Add `async` keyword to function definition
2. Use `await` when calling skills
3. Use `invoke_async` instead of `invoke`

## Migrating from google-generativeai to google-genai SDK

### Before (google-generativeai - No longer supported)
```python
import google.generativeai as genai

genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-1.5-pro')
response = model.generate_content(prompt)
```

### After (google-genai - Required)
```python
from google import genai
from google.genai import types

client = genai.Client(api_key=api_key)
response = client.models.generate_content(
    model='gemini-1.5-pro',
    contents=prompt
)
```

### Environment Variables
Remove `GOOGLE_SDK_TYPE` - only `google-genai` is supported now:
```bash
# Before
GOOGLE_SDK_TYPE=google-generativeai  # Remove this
GOOGLE_API_KEY=your-key

# After  
GOOGLE_API_KEY=your-key  # Only this is needed
```

## Schema File Naming Convention

All contract schemas must use `.schema.json` extension:

### Before
```
catalog/contracts/my_contract.json
```

### After
```
catalog/contracts/my_contract.schema.json
```

## Common Migration Issues and Solutions

### Issue: "Skill 'my-skill' must be async. Synchronous skills are not supported."
**Solution:** Convert your skill to use `async def execute()` as shown above.

### Issue: "Agent 'my-agent' must be async. Synchronous agents are not supported."
**Solution:** Add `async` keyword and use `await` for all async operations.

### Issue: "google-generativeai package is required"
**Solution:** Install `google-genai` instead:
```bash
pip uninstall google-generativeai
pip install google-genai
```

### Issue: "No module named 'magsag.skills.echo'"
**Solution:** The example echo skill has been removed. Create your own async skill instead.

## Testing Your Migration

Run these commands to verify your migration:

```bash
# Validate all schemas
uv run python ops/tools/validate_catalog.py

# Check documentation
uv run python ops/tools/check_docs.py

# Run tests
uv run pytest tests/

# Test a specific agent
echo '{"role":"Engineer","level":"Senior"}' | uv run magsag agent run your-agent
```

## Need Help?

- Review the updated examples in `catalog/skills/` and `catalog/agents/`
- Check `SSOT.md` for current terminology and policies
- Run tests to verify your implementation

## Timeline

These changes are effective immediately. There is no grace period for legacy support.
