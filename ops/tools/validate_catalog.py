#!/usr/bin/env python3
"""Validate catalog YAML and JSON Schema files."""

import json
import sys
from pathlib import Path

import yaml

def validate_catalog():
    """Validate all catalog files."""
    errors = []
    catalog_path = Path("catalog")

    # Validate YAML files
    for yaml_file in catalog_path.rglob("*.yaml"):
        try:
            with open(yaml_file) as f:
                yaml.safe_load(f)
        except Exception as e:
            errors.append(f"Invalid YAML in {yaml_file}: {e}")

    # Validate JSON Schema files
    for json_file in catalog_path.rglob("*.schema.json"):
        try:
            with open(json_file) as f:
                schema = json.load(f)
                if "$schema" not in schema:
                    errors.append(f"Missing $schema in {json_file}")
        except Exception as e:
            errors.append(f"Invalid JSON Schema in {json_file}: {e}")

    if errors:
        for error in errors:
            print(f"❌ {error}", file=sys.stderr)
        return 1

    print("✓ Catalog validation passed")
    return 0

if __name__ == "__main__":
    sys.exit(validate_catalog())
