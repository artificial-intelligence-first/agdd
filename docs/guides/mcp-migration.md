---
title: MCP Client Migration Guide
last_synced: 2025-10-29
description: Guide for migrating skills to MCP client integration with graceful fallback patterns
change_log:
  - 2025-10-29: Initial migration guide created
---

# MCP Client Migration Guide

This guide covers migrating existing skills to support MCP (Model Context Protocol) client integration, enabling skills to access external data sources, tools, and services through standardized MCP servers.

## Overview

### What This Guide Covers

- Updating skill signatures to accept MCP runtime
- Implementing MCP tool invocation logic
- Supporting both MCP and non-MCP execution modes
- Common patterns for graceful fallback and strict MCP requirements
- Troubleshooting common migration issues

### Who Should Read This

- Skill developers adding MCP integration to existing skills
- Developers creating new skills that require external data access
- Teams migrating from direct database/API calls to MCP abstraction

### Prerequisites

Before migrating skills to MCP:

1. **Understand MCP Basics**: Review [mcp-integration.md](./mcp-integration.md) for MCP fundamentals
2. **MCP Servers Configured**: Have appropriate MCP servers configured in `.mcp/servers/`
3. **Python Environment**: Python 3.12+ with `agdd[mcp-server]` installed
4. **Skill Structure**: Existing skill with proper contracts and tests

**Required Knowledge:**
- Python async/await syntax
- JSON Schema validation
- AGDD skill structure (see [agent-development.md](./agent-development.md))

**Installation:**
```bash
# Install MCP support
uv sync --extra mcp-server

# Verify MCP servers are discoverable
ls .mcp/servers/
```

## Migration Steps

### Step 1: Update Skill Signature

Skills need to accept an optional `mcp` parameter to access MCP tools.

#### Before (Legacy Signature)

```python
# catalog/skills/salary-band-lookup/impl/salary_band_lookup.py

def run(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Lookup salary band for a candidate profile."""
    role = payload.get("role", "")
    level = payload.get("level", "")

    # Hardcoded fallback data
    return {
        "currency": "USD",
        "min": 100000,
        "max": 180000,
        "source": "internal-table"
    }
```

**Issues with legacy approach:**
- Hardcoded data
- No access to real-time data sources
- Difficult to update data without code changes

#### After (MCP-Enabled Signature)

```python
# catalog/skills/salary-band-lookup/impl/salary_band_lookup.py
from __future__ import annotations
from typing import Any, Dict, Optional

# Import MCP types
from agdd.mcp import MCPRuntime

def run(
    payload: Dict[str, Any],
    *,
    mcp: Optional[MCPRuntime] = None
) -> Dict[str, Any]:
    """Lookup salary band with MCP support.

    Args:
        payload: Input data with role, level, location
        mcp: Optional MCP runtime for database access

    Returns:
        Salary band with currency, min, max, source
    """
    # Implementation with MCP support (see Step 2)
    pass
```

**Key Changes:**
- Import `MCPRuntime` from `agdd.mcp`
- Add `mcp` as keyword-only optional parameter (`*, mcp: Optional[MCPRuntime] = None`)
- Type hint properly for IDE support
- Document the new parameter in docstring

**Signature Rules:**
1. `mcp` must be keyword-only (after `*`)
2. Must have `Optional[MCPRuntime]` type hint
3. Default value must be `None` for backward compatibility

### Step 2: Implement MCP Logic

Add MCP tool invocation logic while maintaining backward compatibility.

#### Pattern 1: Graceful Fallback (Recommended)

Skills work with or without MCP, falling back to reasonable defaults when MCP is unavailable.

```python
# catalog/skills/salary-band-lookup/impl/salary_band_lookup.py
from __future__ import annotations
import asyncio
from typing import Any, Dict, Optional

from agdd.mcp import MCPRuntime

def run(
    payload: Dict[str, Any],
    *,
    mcp: Optional[MCPRuntime] = None
) -> Dict[str, Any]:
    """Lookup salary band with graceful fallback."""

    # Extract input parameters
    role = payload.get("role", "")
    level = payload.get("level", "")
    location = payload.get("location", "US")

    # Try MCP first if available
    if mcp is not None:
        try:
            # Use asyncio.run for async MCP calls
            result = asyncio.run(_lookup_via_mcp(mcp, role, level, location))
            if result:
                return result
        except Exception as exc:
            # Log error but continue to fallback
            print(f"MCP lookup failed: {exc}, using fallback data")

    # Fallback to static data
    return _fallback_lookup(role, level, location)


async def _lookup_via_mcp(
    mcp: MCPRuntime,
    role: str,
    level: str,
    location: str,
) -> Optional[Dict[str, Any]]:
    """Query salary data via MCP PostgreSQL server."""

    sql = """
        SELECT currency, min_salary, max_salary
        FROM salary_bands
        WHERE role = $1 AND level = $2 AND location = $3
        LIMIT 1
    """

    result = await mcp.query_postgres(
        server_id="pg-readonly",
        sql=sql,
        params=[role, level, location],
    )

    if not result.success:
        raise RuntimeError(f"PostgreSQL query failed: {result.error}")

    # Parse result data
    rows = result.data or []
    if not rows:
        return None

    row = rows[0]
    return {
        "currency": row.get("currency", "USD"),
        "min": row.get("min_salary", 0),
        "max": row.get("max_salary", 0),
        "source": "postgres-via-mcp",
    }


def _fallback_lookup(role: str, level: str, location: str) -> Dict[str, Any]:
    """Static fallback when MCP is unavailable."""

    # Reasonable defaults based on level
    base_band = {"currency": "USD", "min": 100000, "max": 180000}

    if "Senior" in role or "Senior" in level:
        base_band.update(min=150000, max=220000)
    elif "Staff" in role or "Staff" in level:
        base_band.update(min=180000, max=280000)
    elif "Principal" in role or "Principal" in level:
        base_band.update(min=220000, max=350000)

    base_band["source"] = "fallback-static"
    return base_band
```

**Benefits:**
- Works in both MCP and non-MCP environments
- Degrades gracefully on errors
- Useful for development and testing
- Production-ready with real data when MCP is available

#### Pattern 2: Strict MCP Requirement

Some skills require MCP and should fail explicitly when it's unavailable.

```python
# catalog/skills/compliance-check/impl/compliance_check.py
from __future__ import annotations
import asyncio
from typing import Any, Dict, Optional

from agdd.mcp import MCPRuntime

def run(
    payload: Dict[str, Any],
    *,
    mcp: Optional[MCPRuntime] = None
) -> Dict[str, Any]:
    """Compliance check requiring MCP access."""

    # Strict requirement: fail if MCP is unavailable
    if mcp is None:
        raise RuntimeError(
            "Compliance check requires MCP runtime. "
            "Ensure skill declares 'mcp:pg-readonly' permission."
        )

    # Verify required permissions
    if not mcp.check_permission("pg-readonly"):
        raise RuntimeError(
            "Missing required permission: mcp:pg-readonly"
        )

    # Execute MCP-based logic
    return asyncio.run(_check_compliance(mcp, payload))


async def _check_compliance(
    mcp: MCPRuntime,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Execute compliance checks via MCP."""

    candidate_id = payload["candidate_id"]

    # Query compliance database
    result = await mcp.query_postgres(
        server_id="pg-readonly",
        sql="SELECT * FROM compliance_records WHERE candidate_id = $1",
        params=[candidate_id],
    )

    if not result.success:
        raise RuntimeError(f"Compliance query failed: {result.error}")

    # Process compliance data
    records = result.data or []
    return {
        "candidate_id": candidate_id,
        "compliant": len(records) > 0,
        "records": records,
        "source": "compliance-db",
    }
```

**Use Cases:**
- Regulatory compliance checks (must have authoritative data)
- Security audits
- Financial calculations
- Legal documentation

### Step 3: Update Skill Metadata

Skills using MCP must declare required permissions in `catalog/registry/skills.yaml`.

```yaml
# catalog/registry/skills.yaml

skills:
  # Graceful fallback skill (permissions optional but recommended)
  - id: skill.salary-band-lookup
    name: Salary Band Lookup
    version: "0.2.0"
    location: catalog/skills/salary-band-lookup
    entrypoint: catalog/skills/salary-band-lookup/impl/salary_band_lookup.py:run
    permissions:
      - mcp:pg-readonly  # PostgreSQL read access
    contracts:
      input: catalog/contracts/salary_lookup_input.json
      output: catalog/contracts/salary_band.schema.json

  # Strict MCP requirement skill
  - id: skill.compliance-check
    name: Compliance Check
    version: "1.0.0"
    location: catalog/skills/compliance-check
    entrypoint: catalog/skills/compliance-check/impl/compliance_check.py:run
    permissions:
      - mcp:pg-readonly  # Required for compliance database
    contracts:
      input: catalog/contracts/compliance_input.json
      output: catalog/contracts/compliance_result.json
```

**Permission Format:**
- MCP permissions: `mcp:<server-id>` (e.g., `mcp:pg-readonly`, `mcp:filesystem`)
- Server ID must match `.mcp/servers/<server-id>.yaml`

**Best Practices:**
1. Always declare MCP permissions explicitly
2. Use read-only servers when possible (`pg-readonly` vs `pg-readwrite`)
3. Document why each permission is needed
4. Update version when adding MCP support

### Step 4: Test Both Modes

Ensure skills work with and without MCP runtime.

#### Test Without MCP (Fallback Mode)

```python
# catalog/skills/salary-band-lookup/tests/test_salary_band_lookup.py
from catalog.skills.salary_band_lookup.impl.salary_band_lookup import run

def test_salary_lookup_without_mcp():
    """Test skill works without MCP runtime (fallback mode)."""

    payload = {
        "role": "Senior Engineer",
        "level": "Senior",
        "location": "US",
    }

    # Call without mcp parameter
    result = run(payload)

    # Verify fallback data is returned
    assert result["currency"] == "USD"
    assert result["min"] > 0
    assert result["max"] > result["min"]
    assert result["source"] == "fallback-static"


def test_fallback_level_adjustments():
    """Test fallback correctly adjusts for seniority levels."""

    junior_result = run({"role": "Junior Engineer", "level": "Junior"})
    senior_result = run({"role": "Senior Engineer", "level": "Senior"})

    # Senior should have higher salary range
    assert senior_result["min"] > junior_result["min"]
    assert senior_result["max"] > junior_result["max"]
```

#### Test With MCP (Database Mode)

```python
# catalog/skills/salary-band-lookup/tests/test_salary_band_lookup_mcp.py
import pytest
from unittest.mock import AsyncMock, patch
from agdd.mcp import MCPRegistry, MCPRuntime, MCPToolResult

from catalog.skills.salary_band_lookup.impl.salary_band_lookup import run


@pytest.fixture
def mock_mcp_runtime():
    """Create a mock MCP runtime with PostgreSQL access."""
    registry = MCPRegistry()
    runtime = MCPRuntime(registry)
    runtime.grant_permissions(["mcp:pg-readonly"])
    return runtime


def test_salary_lookup_with_mcp(mock_mcp_runtime):
    """Test skill uses MCP when runtime is provided."""

    # Mock PostgreSQL query response
    with patch.object(
        mock_mcp_runtime,
        'query_postgres',
        new_callable=AsyncMock,
    ) as mock_query:

        mock_query.return_value = MCPToolResult(
            success=True,
            data=[
                {
                    "currency": "USD",
                    "min_salary": 160000,
                    "max_salary": 220000,
                }
            ],
        )

        payload = {
            "role": "Senior Engineer",
            "level": "Senior",
            "location": "San Francisco",
        }

        # Call with mcp
        result = run(payload, mcp=mock_mcp_runtime)

        # Verify MCP data is returned
        assert result["currency"] == "USD"
        assert result["min"] == 160000
        assert result["max"] == 220000
        assert result["source"] == "postgres-via-mcp"

        # Verify PostgreSQL was called with correct parameters
        mock_query.assert_called_once_with(
            server_id="pg-readonly",
            sql=pytest.approx.ANY,  # Don't check exact SQL
            params=["Senior Engineer", "Senior", "San Francisco"],
        )


def test_mcp_error_fallback(mock_mcp_runtime):
    """Test skill falls back when MCP query fails."""

    # Mock PostgreSQL query failure
    with patch.object(
        mock_mcp_runtime,
        'query_postgres',
        new_callable=AsyncMock,
    ) as mock_query:

        mock_query.return_value = MCPToolResult(
            success=False,
            error="Connection timeout",
        )

        payload = {"role": "Engineer", "level": "Mid"}

        # Should not raise exception, should fallback
        result = run(payload, mcp=mock_mcp_runtime)

        # Verify fallback data is returned
        assert result["source"] == "fallback-static"
```

## Common Patterns

### Pattern 1: Graceful Fallback (Development-Friendly)

**When to Use:**
- Skills that have reasonable static fallback data
- Development environments without MCP infrastructure
- Non-critical data lookups

**Implementation:**
```python
def run(payload: Dict[str, Any], *, mcp: Optional[MCPRuntime] = None) -> Dict[str, Any]:
    if mcp is not None:
        try:
            return asyncio.run(_try_mcp(mcp, payload))
        except Exception as exc:
            print(f"MCP failed: {exc}, using fallback")

    return _fallback_logic(payload)
```

**Pros:**
- Works everywhere
- Easy to develop and test
- Degrades gracefully

**Cons:**
- May return stale/inaccurate data in fallback mode
- Harder to detect configuration issues

### Pattern 2: Strict MCP Requirement (Production-Safe)

**When to Use:**
- Critical business logic requiring authoritative data
- Compliance, security, or financial operations
- Production-only skills

**Implementation:**
```python
def run(payload: Dict[str, Any], *, mcp: Optional[MCPRuntime] = None) -> Dict[str, Any]:
    if mcp is None:
        raise RuntimeError("Skill requires MCP runtime")

    if not mcp.check_permission("pg-readonly"):
        raise RuntimeError("Missing required permission: mcp:pg-readonly")

    return asyncio.run(_execute_with_mcp(mcp, payload))
```

**Pros:**
- Fails fast when misconfigured
- Guarantees data accuracy
- Clear error messages

**Cons:**
- Cannot run without MCP infrastructure
- Requires proper setup for development/testing

### Pattern 3: Multiple MCP Servers

**When to Use:**
- Skills needing data from multiple sources
- Complex workflows combining file, database, and API access

**Implementation:**
```python
def run(payload: Dict[str, Any], *, mcp: Optional[MCPRuntime] = None) -> Dict[str, Any]:
    if mcp is None:
        raise RuntimeError("Skill requires MCP runtime")

    # Check all required permissions
    required_servers = ["pg-readonly", "filesystem"]
    for server_id in required_servers:
        if not mcp.check_permission(server_id):
            raise RuntimeError(f"Missing permission: mcp:{server_id}")

    return asyncio.run(_multi_server_workflow(mcp, payload))


async def _multi_server_workflow(mcp: MCPRuntime, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Execute workflow using multiple MCP servers."""

    # Query database
    db_result = await mcp.query_postgres(
        server_id="pg-readonly",
        sql="SELECT * FROM candidates WHERE id = $1",
        params=[payload["candidate_id"]],
    )

    if not db_result.success:
        raise RuntimeError(f"Database query failed: {db_result.error}")

    candidate_data = db_result.data[0]

    # Read configuration file
    file_result = await mcp.execute_tool(
        server_id="filesystem",
        tool_name="read_file",
        arguments={"path": "config/bands.json"},
    )

    if not file_result.success:
        raise RuntimeError(f"File read failed: {file_result.error}")

    # Combine data from multiple sources
    return {
        "candidate": candidate_data,
        "config": file_result.data,
        "source": "multi-server",
    }
```

**Skill Metadata:**
```yaml
skills:
  - id: skill.multi-source-lookup
    name: Multi-Source Data Lookup
    version: "1.0.0"
    location: catalog/skills/multi-source-lookup
    entrypoint: catalog/skills/multi-source-lookup/impl/multi_source.py:run
    permissions:
      - mcp:pg-readonly    # Database access
      - mcp:filesystem     # File access
```

## Troubleshooting

### Common Error: Permission Denied

**Error Message:**
```
Permission denied: skill does not have access to server 'pg-readonly'.
Required permission: mcp:pg-readonly
```

**Cause:**
Skill attempted to use MCP server without declaring required permission.

**Solution:**
Add permission to skill metadata in `catalog/registry/skills.yaml`:

```yaml
skills:
  - id: skill.your-skill
    permissions:
      - mcp:pg-readonly  # Add this line
```

**Verification:**
```bash
# Check skill permissions are loaded
uv run python -c "
from agdd.registry import Registry
registry = Registry()
skill = registry.load_skill('skill.your-skill')
print('Permissions:', skill.permissions)
"
```

### Common Error: MCP Runtime Not Provided

**Error Message:**
```
RuntimeError: Compliance check requires MCP runtime.
Ensure skill declares 'mcp:pg-readonly' permission.
```

**Cause:**
Skill requires MCP but `mcp` is `None` (not provided by runner).

**Solutions:**

**Solution 1: Make Skill More Flexible (Add Fallback)**
```python
def run(payload: Dict[str, Any], *, mcp: Optional[MCPRuntime] = None) -> Dict[str, Any]:
    # Remove strict requirement, add fallback
    if mcp is None:
        return _fallback_logic(payload)  # Instead of raising

    return asyncio.run(_execute_with_mcp(mcp, payload))
```

**Solution 2: Ensure Permissions Are Declared**
```yaml
# catalog/registry/skills.yaml
skills:
  - id: skill.your-skill
    permissions:
      - mcp:pg-readonly  # Declare permission
```

**Solution 3: Check MCP Server Configuration**
```bash
# Verify MCP server exists
ls .mcp/servers/pg-readonly.yaml

# Verify server configuration is valid
cat .mcp/servers/pg-readonly.yaml
```

### Common Error: Missing Dependencies

**Error Message:**
```
ImportError: No module named 'agdd.mcp'
```

**Cause:**
MCP dependencies not installed.

**Solution:**
```bash
# Install MCP support
uv sync --extra mcp-server

# Verify installation
uv run python -c "from agdd.mcp import MCPRuntime; print('MCP installed')"
```

### Common Error: Async Execution Failed

**Error Message:**
```
RuntimeError: asyncio.run() cannot be called from a running event loop
```

**Cause:**
Attempting to use `asyncio.run()` from within an already-running async context.

**Solution 1: Use Async Skill Signature (Future)**
```python
# If runner supports async skills (future feature)
async def run(
    payload: Dict[str, Any],
    *,
    mcp: Optional[MCPRuntime] = None
) -> Dict[str, Any]:
    # Can await directly
    result = await mcp.query_postgres(...)
    return result
```

**Solution 2: Use `asyncio.run()` in Sync Skills (Current)**
```python
# Current approach for sync skills
def run(payload: Dict[str, Any], *, mcp: Optional[MCPRuntime] = None) -> Dict[str, Any]:
    # Create new event loop
    return asyncio.run(_async_logic(mcp, payload))
```

**Solution 3: Get Existing Event Loop**
```python
def run(payload: Dict[str, Any], *, mcp: Optional[MCPRuntime] = None) -> Dict[str, Any]:
    try:
        # Try to get existing event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Running in async context, create task
            return asyncio.ensure_future(_async_logic(mcp, payload))
        else:
            # Not running, use asyncio.run
            return asyncio.run(_async_logic(mcp, payload))
    except RuntimeError:
        # No event loop exists, create one
        return asyncio.run(_async_logic(mcp, payload))
```

### Common Error: Server Not Started

**Error Message:**
```
MCPServerError: Server 'pg-readonly' not started
```

**Cause:**
MCP server configuration exists but server hasn't been initialized.

**Solution:**
Servers are started on-demand. Check for configuration errors:

```bash
# Verify server configuration
cat .mcp/servers/pg-readonly.yaml

# Check for environment variables
echo $PG_RO_URL  # Should print connection string

# Test server manually
npx -y @modelcontextprotocol/server-postgres "$PG_RO_URL"
```

**Configuration Example:**
```yaml
# .mcp/servers/pg-readonly.yaml
server_id: pg-readonly
type: postgres
description: Read-only PostgreSQL database access
scopes:
  - read:tables
conn:
  url_env: PG_RO_URL  # Must be set in environment
limits:
  rate_per_min: 120
  timeout_s: 30
```

## Best Practices

### Error Handling

**1. Distinguish Between Errors and Missing Data**
```python
async def _lookup_via_mcp(mcp: MCPRuntime, role: str) -> Optional[Dict[str, Any]]:
    result = await mcp.query_postgres(...)

    if not result.success:
        # Server error - raise exception
        raise RuntimeError(f"Query failed: {result.error}")

    if not result.data:
        # No data found - return None (not an error)
        return None

    return result.data[0]
```

**2. Provide Context in Error Messages**
```python
try:
    result = await mcp.query_postgres(server_id="pg-readonly", sql=sql, params=params)
except Exception as exc:
    raise RuntimeError(
        f"Failed to query salary bands for role={role}, level={level}: {exc}"
    ) from exc
```

**3. Log Errors Before Fallback**
```python
import logging
logger = logging.getLogger(__name__)

def run(payload: Dict[str, Any], *, mcp: Optional[MCPRuntime] = None) -> Dict[str, Any]:
    if mcp is not None:
        try:
            return asyncio.run(_try_mcp(mcp, payload))
        except Exception as exc:
            logger.warning(f"MCP lookup failed, using fallback: {exc}")

    return _fallback_logic(payload)
```

### Logging

**1. Log MCP Usage**
```python
def run(payload: Dict[str, Any], *, mcp: Optional[MCPRuntime] = None) -> Dict[str, Any]:
    logger = logging.getLogger(__name__)

    if mcp is None:
        logger.info("Running in fallback mode (no MCP runtime)")
        return _fallback_logic(payload)

    logger.info(f"Using MCP runtime with permissions: {mcp.get_granted_permissions()}")
    return asyncio.run(_execute_with_mcp(mcp, payload))
```

**2. Log Query Performance**
```python
import time

async def _query_with_logging(mcp: MCPRuntime, server_id: str, sql: str, params: list) -> MCPToolResult:
    logger = logging.getLogger(__name__)

    start_time = time.time()
    result = await mcp.query_postgres(server_id=server_id, sql=sql, params=params)
    duration = time.time() - start_time

    logger.info(f"PostgreSQL query completed in {duration:.2f}s, success={result.success}")

    return result
```

### Testing

**1. Test Matrix: MCP Available/Unavailable**
```python
@pytest.mark.parametrize("has_mcp", [True, False])
def test_skill_with_and_without_mcp(has_mcp, mock_mcp_runtime):
    """Test skill behavior with and without MCP."""

    payload = {"role": "Engineer"}

    if has_mcp:
        result = run(payload, mcp=mock_mcp_runtime)
        assert result["source"] == "postgres-via-mcp"
    else:
        result = run(payload)
        assert result["source"] == "fallback-static"
```

**2. Test Permission Checks**
```python
def test_permission_denied(mock_mcp_runtime):
    """Test behavior when permission is missing."""

    # Don't grant required permission
    mock_mcp_runtime.revoke_permissions(["mcp:pg-readonly"])

    payload = {"role": "Engineer"}

    # Should either fail gracefully or fall back
    result = run(payload, mcp=mock_mcp_runtime)

    # Verify fallback was used
    assert result["source"] != "postgres-via-mcp"
```

**3. Integration Tests with Real MCP Servers**
```python
@pytest.mark.integration
def test_real_mcp_integration():
    """Integration test with actual MCP server (requires setup)."""

    registry = MCPRegistry()
    registry.discover_servers()

    runtime = MCPRuntime(registry)
    runtime.grant_permissions(["mcp:pg-readonly"])

    payload = {"role": "Senior Engineer", "level": "Senior"}
    result = run(payload, mcp=runtime)

    # Verify real data was returned
    assert result["source"] == "postgres-via-mcp"
    assert result["min"] > 0
```

### Performance Considerations

**1. Connection Pooling**

MCP servers handle connection pooling automatically. Don't create multiple runtime instances:

**Bad:**
```python
def run(payload: Dict[str, Any], *, mcp: Optional[MCPRuntime] = None) -> Dict[str, Any]:
    # Don't create new connections per call
    for item in payload["items"]:
        # Each call uses pooled connections, but creating runtime per item is wasteful
        local_runtime = MCPRuntime(registry)  # BAD!
        result = asyncio.run(local_runtime.query_postgres(...))
```

**Good:**
```python
def run(payload: Dict[str, Any], *, mcp: Optional[MCPRuntime] = None) -> Dict[str, Any]:
    # Reuse provided runtime
    if mcp is None:
        raise RuntimeError("MCP runtime required")

    # Runtime reuses connections from pool
    return asyncio.run(_batch_lookup(mcp, payload["items"]))
```

**2. Batch Queries**

Combine multiple queries when possible:

```python
async def _batch_lookup(mcp: MCPRuntime, items: list) -> Dict[str, Any]:
    # Single query for multiple items
    sql = "SELECT * FROM salary_bands WHERE role = ANY($1)"
    roles = [item["role"] for item in items]

    result = await mcp.query_postgres(
        server_id="pg-readonly",
        sql=sql,
        params=[roles],
    )

    return result.data
```

**3. Cache Results**

For frequently accessed data:

```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def _cached_static_data(key: str) -> Dict[str, Any]:
    """Cache static fallback data."""
    return _compute_fallback(key)


def run(payload: Dict[str, Any], *, mcp: Optional[MCPRuntime] = None) -> Dict[str, Any]:
    if mcp is None:
        # Use cached fallback
        return _cached_static_data(payload["role"])

    # Fresh MCP data
    return asyncio.run(_lookup_via_mcp(mcp, payload))
```

## Complete Examples

### Example 1: PostgreSQL Salary Lookup

Complete migration from hardcoded data to PostgreSQL via MCP.

**File Structure:**
```
catalog/skills/salary-band-lookup/
├── impl/
│   └── salary_band_lookup.py
├── tests/
│   ├── test_salary_band_lookup.py
│   └── test_salary_band_lookup_mcp.py
└── README.md
```

**Implementation:**
```python
# catalog/skills/salary-band-lookup/impl/salary_band_lookup.py
"""Salary Band Lookup Skill with MCP PostgreSQL integration."""
from __future__ import annotations
import asyncio
import logging
from typing import Any, Dict, Optional

from agdd.mcp import MCPRuntime

logger = logging.getLogger(__name__)


def run(
    payload: Dict[str, Any],
    *,
    mcp: Optional[MCPRuntime] = None
) -> Dict[str, Any]:
    """Lookup salary band with PostgreSQL via MCP.

    Args:
        payload: {role: str, level: str, location: str}
        mcp: Optional MCP runtime for database access

    Returns:
        {currency: str, min: int, max: int, source: str}
    """
    role = payload.get("role", "")
    level = payload.get("level", "")
    location = payload.get("location", "US")

    # Try MCP first
    if mcp is not None:
        logger.info(f"Attempting MCP lookup for {role}/{level}/{location}")
        try:
            result = asyncio.run(_lookup_via_mcp(mcp, role, level, location))
            if result:
                logger.info(f"MCP lookup successful: {result['source']}")
                return result
        except Exception as exc:
            logger.warning(f"MCP lookup failed: {exc}, using fallback")
    else:
        logger.info("No MCP runtime provided, using fallback")

    # Fallback to static data
    return _fallback_lookup(role, level, location)


async def _lookup_via_mcp(
    mcp: MCPRuntime,
    role: str,
    level: str,
    location: str,
) -> Optional[Dict[str, Any]]:
    """Query salary data via MCP PostgreSQL server."""

    # Check permission
    if not mcp.check_permission("pg-readonly"):
        raise RuntimeError("Missing required permission: mcp:pg-readonly")

    # Build query
    sql = """
        SELECT currency, min_salary, max_salary, effective_date
        FROM salary_bands
        WHERE role = $1 AND level = $2 AND location = $3
        ORDER BY effective_date DESC
        LIMIT 1
    """

    # Execute query
    result = await mcp.query_postgres(
        server_id="pg-readonly",
        sql=sql,
        params=[role, level, location],
    )

    # Handle errors
    if not result.success:
        raise RuntimeError(f"PostgreSQL query failed: {result.error}")

    # Parse results
    rows = result.data or []
    if not rows:
        logger.info(f"No salary data found for {role}/{level}/{location}")
        return None

    row = rows[0]
    return {
        "currency": row.get("currency", "USD"),
        "min": row.get("min_salary", 0),
        "max": row.get("max_salary", 0),
        "source": "postgres-via-mcp",
        "effective_date": row.get("effective_date"),
    }


def _fallback_lookup(role: str, level: str, location: str) -> Dict[str, Any]:
    """Static fallback data when MCP is unavailable."""

    # Default band
    band = {"currency": "USD", "min": 100000, "max": 180000}

    # Level adjustments
    if "Principal" in role or "Principal" in level:
        band.update(min=220000, max=350000)
    elif "Staff" in role or "Staff" in level:
        band.update(min=180000, max=280000)
    elif "Senior" in role or "Senior" in level:
        band.update(min=150000, max=220000)
    elif "Junior" in role or "Junior" in level:
        band.update(min=80000, max=120000)

    # Location adjustments
    if "San Francisco" in location or "Bay Area" in location:
        band["min"] = int(band["min"] * 1.2)
        band["max"] = int(band["max"] * 1.2)
    elif "New York" in location or "NYC" in location:
        band["min"] = int(band["min"] * 1.15)
        band["max"] = int(band["max"] * 1.15)

    band["source"] = "fallback-static"
    return band
```

**Skill Metadata:**
```yaml
# catalog/registry/skills.yaml
skills:
  - id: skill.salary-band-lookup
    name: Salary Band Lookup
    version: "0.2.0"
    location: catalog/skills/salary-band-lookup
    entrypoint: catalog/skills/salary-band-lookup/impl/salary_band_lookup.py:run
    permissions:
      - mcp:pg-readonly
    contracts:
      input: catalog/contracts/salary_lookup_input.json
      output: catalog/contracts/salary_band.schema.json
```

**MCP Server Configuration:**
```yaml
# .mcp/servers/pg-readonly.yaml
server_id: pg-readonly
type: postgres
description: Read-only PostgreSQL database for salary data
scopes:
  - read:tables
conn:
  url_env: PG_RO_URL
limits:
  rate_per_min: 120
  timeout_s: 30
```

**Environment Setup:**
```bash
# .env
PG_RO_URL=postgresql://readonly:password@localhost:5432/compensation_db
```

### Example 2: Web Content Fetch

Skill using fetch MCP server for web scraping.

**Implementation:**
```python
# catalog/skills/web-content-fetch/impl/web_fetch.py
"""Web Content Fetch Skill using fetch MCP server."""
from __future__ import annotations
import asyncio
import logging
from typing import Any, Dict, Optional

from agdd.mcp import MCPRuntime

logger = logging.getLogger(__name__)


def run(
    payload: Dict[str, Any],
    *,
    mcp: Optional[MCPRuntime] = None
) -> Dict[str, Any]:
    """Fetch web content via MCP fetch server.

    Args:
        payload: {url: str, extract_text: bool}
        mcp: MCP runtime for web fetch

    Returns:
        {url: str, success: bool, title: str, content: str, metadata: dict}
    """
    if mcp is None:
        raise RuntimeError("Web fetch requires MCP runtime with mcp:fetch permission")

    url = payload.get("url")
    if not url:
        raise ValueError("Missing required field: url")

    extract_text = payload.get("extract_text", True)

    return asyncio.run(_fetch_web_content(mcp, url, extract_text))


async def _fetch_web_content(
    mcp: MCPRuntime,
    url: str,
    extract_text: bool,
) -> Dict[str, Any]:
    """Fetch web content via MCP."""

    # Check permission
    if not mcp.check_permission("fetch"):
        raise RuntimeError("Missing required permission: mcp:fetch")

    # Determine tool based on desired output
    tool_name = "fetch_markdown" if extract_text else "fetch_url"

    # Execute fetch
    result = await mcp.execute_tool(
        server_id="fetch",
        tool_name=tool_name,
        arguments={"url": url},
    )

    if not result.success:
        return {
            "url": url,
            "success": False,
            "error": result.error,
            "metadata": {"status_code": 0},
        }

    # Parse response
    data = result.data or {}
    return {
        "url": url,
        "success": True,
        "title": data.get("title", ""),
        "content": data.get("content", ""),
        "metadata": {
            "status_code": data.get("status_code", 200),
            "content_type": data.get("content_type", ""),
            "extracted_text": extract_text,
        },
    }
```

**Skill Metadata:**
```yaml
# catalog/registry/skills.yaml
skills:
  - id: skill.web-content-fetch
    name: Web Content Fetch
    version: "1.0.0"
    location: catalog/skills/web-content-fetch
    entrypoint: catalog/skills/web-content-fetch/impl/web_fetch.py:run
    permissions:
      - mcp:fetch
    contracts:
      input: catalog/contracts/web_fetch_input.json
      output: catalog/contracts/web_fetch_result.json
```

### Example 3: Multi-Server Skill

Skill using both PostgreSQL and filesystem MCP servers.

**Implementation:**
```python
# catalog/skills/candidate-profile-builder/impl/profile_builder.py
"""Candidate Profile Builder using multiple MCP servers."""
from __future__ import annotations
import asyncio
import json
import logging
from typing import Any, Dict, Optional

from agdd.mcp import MCPRuntime

logger = logging.getLogger(__name__)


def run(
    payload: Dict[str, Any],
    *,
    mcp: Optional[MCPRuntime] = None
) -> Dict[str, Any]:
    """Build candidate profile from database and filesystem.

    Args:
        payload: {candidate_id: str}
        mcp: MCP runtime with pg-readonly and filesystem access

    Returns:
        {candidate: dict, skills: list, certifications: list}
    """
    if mcp is None:
        raise RuntimeError("Profile builder requires MCP runtime")

    # Verify all required permissions
    required = ["pg-readonly", "filesystem"]
    for server_id in required:
        if not mcp.check_permission(server_id):
            raise RuntimeError(f"Missing required permission: mcp:{server_id}")

    candidate_id = payload.get("candidate_id")
    if not candidate_id:
        raise ValueError("Missing required field: candidate_id")

    return asyncio.run(_build_profile(mcp, candidate_id))


async def _build_profile(
    mcp: MCPRuntime,
    candidate_id: str,
) -> Dict[str, Any]:
    """Build profile using multiple MCP servers."""

    # Query candidate data from PostgreSQL
    logger.info(f"Fetching candidate data for {candidate_id}")
    candidate_result = await mcp.query_postgres(
        server_id="pg-readonly",
        sql="SELECT * FROM candidates WHERE id = $1",
        params=[candidate_id],
    )

    if not candidate_result.success:
        raise RuntimeError(f"Failed to fetch candidate: {candidate_result.error}")

    if not candidate_result.data:
        raise ValueError(f"Candidate not found: {candidate_id}")

    candidate_data = candidate_result.data[0]

    # Query skills from PostgreSQL
    logger.info(f"Fetching skills for {candidate_id}")
    skills_result = await mcp.query_postgres(
        server_id="pg-readonly",
        sql="SELECT skill_name, proficiency FROM candidate_skills WHERE candidate_id = $1",
        params=[candidate_id],
    )

    if not skills_result.success:
        logger.warning(f"Failed to fetch skills: {skills_result.error}")
        skills = []
    else:
        skills = skills_result.data or []

    # Read certifications from filesystem
    logger.info(f"Reading certifications file for {candidate_id}")
    cert_file = f"data/certifications/{candidate_id}.json"
    cert_result = await mcp.execute_tool(
        server_id="filesystem",
        tool_name="read_file",
        arguments={"path": cert_file},
    )

    if not cert_result.success:
        logger.warning(f"Failed to read certifications: {cert_result.error}")
        certifications = []
    else:
        try:
            cert_content = cert_result.data.get("content", "[]")
            certifications = json.loads(cert_content)
        except json.JSONDecodeError as exc:
            logger.error(f"Invalid JSON in certifications file: {exc}")
            certifications = []

    # Combine all data
    return {
        "candidate": {
            "id": candidate_data.get("id"),
            "name": candidate_data.get("name"),
            "email": candidate_data.get("email"),
            "location": candidate_data.get("location"),
        },
        "skills": skills,
        "certifications": certifications,
        "source": "multi-server-mcp",
    }
```

**Skill Metadata:**
```yaml
# catalog/registry/skills.yaml
skills:
  - id: skill.candidate-profile-builder
    name: Candidate Profile Builder
    version: "1.0.0"
    location: catalog/skills/candidate-profile-builder
    entrypoint: catalog/skills/candidate-profile-builder/impl/profile_builder.py:run
    permissions:
      - mcp:pg-readonly
      - mcp:filesystem
    contracts:
      input: catalog/contracts/profile_builder_input.json
      output: catalog/contracts/candidate_profile.schema.json
```

## Timeline and Status

### Phase 1: Infrastructure (Completed - v0.1.0)

**Status:** ✅ Complete

- [x] MCP Registry for server discovery
- [x] MCP Runtime for permission enforcement
- [x] MCP tool execution with asyncio support
- [x] PostgreSQL server adapter
- [x] Integration tests

### Phase 2: Skill Migration (Completed - v0.2.0)

**Status:** ✅ Complete

**Delivered:**
- Async skill signatures with optional `mcp` parameter across catalog templates
- Automatic MCP runtime injection via `SkillRuntime`
- Updated sample skills (`doc-gen`, `task-decomposition`, `result-aggregation`) running in Phase 2 mode with graceful fallbacks
- Test patterns for dual-mode (MCP/non-MCP) execution
- This migration guide reflecting the new baseline

### Phase 3: Production Hardening (Planned - v0.3.0)

**Status:** 📋 Planned

- [ ] Connection pooling optimization
- [ ] Circuit breaker for failing MCP servers
- [ ] Request/response caching
- [ ] Distributed tracing for MCP calls
- [ ] Cost tracking per MCP server
- [ ] SLO enforcement for MCP-dependent skills

## Next Steps

### Checklist for Migration

Use this checklist when migrating a skill to MCP:

- [ ] **1. Review Skill Requirements**
  - [ ] Identify what external data/tools the skill needs
  - [ ] Determine which MCP servers provide required functionality
  - [ ] Verify MCP servers are configured in `.mcp/servers/`

- [ ] **2. Update Skill Code**
  - [ ] Add `mcp` parameter to `run()` function
  - [ ] Import `MCPRuntime` from `agdd.mcp`
  - [ ] Implement MCP logic with graceful fallback
  - [ ] Add permission checks
  - [ ] Handle async execution properly

- [ ] **3. Update Skill Metadata**
  - [ ] Declare MCP permissions in `catalog/registry/skills.yaml`
  - [ ] Increment skill version
  - [ ] Update skill description

- [ ] **4. Write Tests**
  - [ ] Test without MCP (fallback mode)
  - [ ] Test with MCP (mock runtime)
  - [ ] Test permission denied scenarios
  - [ ] Test error handling and recovery

- [ ] **5. Documentation**
  - [ ] Update skill README.md
  - [ ] Document MCP requirements
  - [ ] Add usage examples
  - [ ] Document fallback behavior

- [ ] **6. Integration Testing**
  - [ ] Test with real MCP servers locally
  - [ ] Verify permissions are enforced
  - [ ] Check performance and latency
  - [ ] Test error scenarios

- [ ] **7. Deployment**
  - [ ] Update MCP server configurations in production
  - [ ] Set required environment variables
  - [ ] Deploy skill with new version
  - [ ] Monitor MCP call metrics

### Links to Related Documentation

**Core Documentation:**
- [MCP Integration Guide](./mcp-integration.md) - Overview of MCP in AGDD
- [Agent Development Guide](./agent-development.md) - Building agents and skills
- [MCP Server Guide](./mcp-server.md) - Exposing agents as MCP tools

**Advanced Topics:**
- [Multi-Provider Guide](./multi-provider.md) - LLM provider configuration
- [Cost Optimization](./cost-optimization.md) - Managing costs including MCP
- [Storage Layer](../storage.md) - Querying MCP usage data

**Reference:**
- [Model Context Protocol Specification](https://modelcontextprotocol.io/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [AGDD SSOT](../architecture/ssot.md) - Terminology and policies

---

**Last Updated:** 2025-10-29
**Version:** 1.0.0
**Maintainer:** AGDD Core Team
