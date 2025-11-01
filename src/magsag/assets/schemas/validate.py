#!/usr/bin/env python3
"""
Validation script for MAGSAG JSON Schemas.

Usage:
    python validate.py event <json_file>
    python validate.py error <json_file>
    python validate.py artifacts <json_file>
    python validate.py all <json_file>

Examples:
    # Validate an event envelope
    python validate.py event sample_event.json

    # Validate all schemas against their examples
    python validate.py self-test

Dependencies:
    pip install jsonschema
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple, cast

try:
    from jsonschema import Draft7Validator
except ImportError:
    print("Error: jsonschema package not found.", file=sys.stderr)
    print("Install it with: pip install jsonschema", file=sys.stderr)
    sys.exit(1)


SCHEMA_DIR = Path(__file__).parent
JSONDict = Dict[str, Any]


SCHEMAS: Dict[str, Path] = {
    "event": SCHEMA_DIR / "event.schema.json",
    "error": SCHEMA_DIR / "error.schema.json",
    "artifacts": SCHEMA_DIR / "artifacts.schema.json",
}


def load_json(path: Path) -> JSONDict:
    """Load JSON from file."""
    with open(path, "r", encoding="utf-8") as f:
        return cast(JSONDict, json.load(f))


def validate_instance(
    schema_name: str, instance: JSONDict
) -> Tuple[bool, List[str]]:
    """
    Validate a JSON instance against a schema.

    Args:
        schema_name: Name of the schema (event, error, artifacts)
        instance: JSON data to validate

    Returns:
        Tuple of (is_valid, error_messages)
    """
    schema_path = SCHEMAS.get(schema_name)
    if not schema_path:
        return False, [f"Unknown schema: {schema_name}"]

    if not schema_path.exists():
        return False, [f"Schema file not found: {schema_path}"]

    schema = load_json(schema_path)
    validator = Draft7Validator(schema)
    errors = list(validator.iter_errors(instance))

    if not errors:
        return True, []

    error_messages = []
    for error in errors:
        path = ".".join(str(p) for p in error.absolute_path) or "root"
        error_messages.append(f"  [{path}] {error.message}")

    return False, error_messages


def validate_file(schema_name: str, json_path: Path) -> bool:
    """
    Validate a JSON file against a schema.

    Args:
        schema_name: Name of the schema
        json_path: Path to JSON file

    Returns:
        True if valid, False otherwise
    """
    print(f"Validating {json_path} against {schema_name} schema...")

    try:
        instance = load_json(json_path)
    except json.JSONDecodeError as e:
        print(f"✗ Invalid JSON: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"✗ Failed to load file: {e}", file=sys.stderr)
        return False

    is_valid, errors = validate_instance(schema_name, instance)

    if is_valid:
        print("✓ Valid")
        return True
    else:
        print("✗ Validation failed:", file=sys.stderr)
        for error in errors:
            print(error, file=sys.stderr)
        return False


def self_test() -> bool:
    """
    Validate all schemas against their embedded examples.

    Returns:
        True if all examples are valid, False otherwise
    """
    print("Running self-test: validating schema examples...\n")

    all_valid = True

    for schema_name, schema_path in SCHEMAS.items():
        print(f"Testing {schema_name} schema...")

        if not schema_path.exists():
            print(f"✗ Schema file not found: {schema_path}", file=sys.stderr)
            all_valid = False
            continue

        schema = load_json(schema_path)
        examples = schema.get("examples", [])

        if not examples:
            print("  ⚠ No examples found in schema")
            continue

        for i, example in enumerate(examples):
            is_valid, errors = validate_instance(schema_name, example)
            if is_valid:
                print(f"  ✓ Example {i+1} is valid")
            else:
                print(f"  ✗ Example {i+1} failed:", file=sys.stderr)
                for error in errors:
                    print(f"    {error}", file=sys.stderr)
                all_valid = False

        print()

    if all_valid:
        print("✓ All self-tests passed")
    else:
        print("✗ Some self-tests failed", file=sys.stderr)

    return all_valid


def main() -> None:
    """Main entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "self-test":
        success = self_test()
        sys.exit(0 if success else 1)

    if command == "all":
        if len(sys.argv) < 3:
            print("Error: JSON file path required", file=sys.stderr)
            print(__doc__)
            sys.exit(1)

        json_path = Path(sys.argv[2])
        all_valid = True

        for schema_name in SCHEMAS.keys():
            if not validate_file(schema_name, json_path):
                all_valid = False
            print()

        sys.exit(0 if all_valid else 1)

    if command in SCHEMAS:
        if len(sys.argv) < 3:
            print("Error: JSON file path required", file=sys.stderr)
            print(__doc__)
            sys.exit(1)

        json_path = Path(sys.argv[2])
        success = validate_file(command, json_path)
        sys.exit(0 if success else 1)

    print(f"Error: Unknown command '{command}'", file=sys.stderr)
    print(f"Available commands: {', '.join(SCHEMAS.keys())}, all, self-test")
    sys.exit(1)


if __name__ == "__main__":
    main()
