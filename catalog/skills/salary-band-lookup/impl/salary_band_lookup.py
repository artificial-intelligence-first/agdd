"""
Salary Band Lookup Skill

Simple implementation providing salary bands based on role and level.
Production version should integrate with MCP server (pg-readonly) for actual data.
"""

from typing import Any, Dict


def run(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lookup salary band for a candidate profile.

    Args:
        payload: Candidate profile with 'role', 'level', 'location' fields

    Returns:
        Salary band with currency, min, max, and source
    """
    role = payload.get("role", "")
    level = payload.get("level", "")
    location = payload.get("location", "")

    # Default band (fallback)
    band = {"currency": "USD", "min": 100000, "max": 180000, "source": "internal-table"}

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
        band["source"] = "internal-table+location-adjustment"
    elif "New York" in location or "NYC" in location:
        band["min"] = int(band["min"] * 1.15)
        band["max"] = int(band["max"] * 1.15)
        band["source"] = "internal-table+location-adjustment"

    return band
