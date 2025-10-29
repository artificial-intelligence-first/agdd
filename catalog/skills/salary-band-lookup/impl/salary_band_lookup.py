"""
Salary Band Lookup Skill - Phase 2 MCP Integration

This skill demonstrates full MCP integration with PostgreSQL database support.

The skill follows a graceful degradation pattern:
1. If MCP runtime is available, attempts to query the PostgreSQL database (pg-readonly)
2. If MCP is unavailable or query fails, falls back to mock logic-based salary bands
3. This ensures backward compatibility while enabling database-driven functionality

MCP Integration:
- Requires permission: mcp:pg-readonly
- Database query: SELECT currency, min_salary, max_salary FROM salary_bands
- Fallback: Logic-based salary bands with role/level/location adjustments
"""

import logging
from typing import Any, Dict, Optional

from agdd.mcp.runtime import MCPRuntime

logger = logging.getLogger(__name__)


async def run(payload: Dict[str, Any], mcp: Optional[MCPRuntime] = None) -> Dict[str, Any]:
    """
    Lookup salary band for a candidate profile.

    This function supports both MCP database-driven and mock fallback modes:
    - With MCP: Queries PostgreSQL database for accurate salary band data
    - Without MCP: Uses logic-based salary bands as fallback

    Args:
        payload: Candidate profile with 'role', 'level', 'location' fields
        mcp: Optional MCP runtime for database access (requires mcp:pg-readonly permission)

    Returns:
        Salary band dictionary with:
        - currency: Currency code (e.g., "USD")
        - min: Minimum salary in the band
        - max: Maximum salary in the band
        - source: Data source ("database" or "mock-fallback")
    """
    role = payload.get("role", "")
    level = payload.get("level", "")
    location = payload.get("location", "")

    # Try MCP database query first if available
    if mcp is not None:
        try:
            logger.info(f"Querying database for salary band: role={role}, level={level}, location={location}")

            result = await mcp.query_postgres(
                server_id="pg-readonly",
                sql="SELECT currency, min_salary, max_salary, 'database' as source FROM salary_bands WHERE role = $1 AND level = $2 AND location = $3 LIMIT 1",
                params=[role, level, location],
            )

            if result.success and result.output:
                rows = result.output.get("rows", [])
                if rows:
                    db_row = rows[0]
                    logger.info("Database query successful, returning database result")
                    return {
                        "currency": db_row.get("currency", "USD"),
                        "min": db_row.get("min_salary", 0),
                        "max": db_row.get("max_salary", 0),
                        "source": "database",
                    }
                else:
                    logger.info("Database query returned no rows, falling back to mock logic")
            else:
                logger.warning(f"Database query failed: {result.error}")

        except Exception as e:
            logger.warning(f"MCP database query failed: {e}, falling back to mock logic")

    # Fallback to mock logic-based salary bands
    logger.info("Using mock fallback logic for salary band calculation")

    # Default band (fallback)
    band = {"currency": "USD", "min": 100000, "max": 180000, "source": "mock-fallback"}

    # Simple level-based adjustments
    if "Senior" in role or "Senior" in level:
        band.update(min=150000, max=220000)
    elif "Staff" in role or "Staff" in level:
        band.update(min=180000, max=280000)
    elif "Principal" in role or "Principal" in level:
        band.update(min=220000, max=350000)
    elif "Junior" in role or "Junior" in level:
        band.update(min=80000, max=120000)

    # Location adjustments (simplified)
    if "San Francisco" in location or "SF" in location or "Bay Area" in location:
        band["min"] = int(band["min"] * 1.2)
        band["max"] = int(band["max"] * 1.2)
    elif "New York" in location or "NYC" in location:
        band["min"] = int(band["min"] * 1.15)
        band["max"] = int(band["max"] * 1.15)

    return band
