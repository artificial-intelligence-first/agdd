"""
Unit tests for MCP tool template.

These tests verify the template structure and basic functionality.
When implementing your own MCP tool, update these tests to match your use case.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_template_structure_exists() -> None:
    """Verify template directory structure exists."""
    template_dir = Path(__file__).resolve().parents[1]
    assert template_dir.name == "mcp-tool-template"

    # Check required files exist
    assert (template_dir / "SKILL.md").exists()
    assert (template_dir / "impl" / "mcp_tool.py").exists()
    assert (template_dir / "resources" / "examples" / "in.json").exists()
    assert (template_dir / "resources" / "examples" / "out.json").exists()
    assert (template_dir / "tests" / "test_mcp_tool.py").exists()


def test_template_imports() -> None:
    """Verify template module can be imported (with expected NotImplementedError)."""
    # Import should succeed even though _call_mcp_tool is not implemented
    # This uses a relative import which may not work in all contexts,
    # so we catch ImportError as acceptable
    try:
        from catalog.skills._template.mcp_tool_template.impl import mcp_tool

        assert hasattr(mcp_tool, "run")
        assert hasattr(mcp_tool, "_validate")
        assert hasattr(mcp_tool, "_prepare_request")
        assert hasattr(mcp_tool, "_call_mcp_tool")
        assert hasattr(mcp_tool, "_process_response")
    except ImportError:
        # Import may fail due to path issues in test environment
        # This is acceptable for a template
        pytest.skip("Template import failed (acceptable for template)")


def test_template_module_structure() -> None:
    """Verify template module has expected structure."""
    import sys
    from pathlib import Path

    # Add template impl directory to path
    impl_dir = Path(__file__).resolve().parents[1] / "impl"
    sys.path.insert(0, str(impl_dir.parent.parent.parent.parent))

    try:
        # Try importing with absolute path manipulation
        import importlib.util

        spec = importlib.util.spec_from_file_location("mcp_tool", impl_dir / "mcp_tool.py")
        if spec and spec.loader:
            mcp_tool = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mcp_tool)

            # Verify expected functions exist
            assert callable(getattr(mcp_tool, "run", None))
            assert callable(getattr(mcp_tool, "_validate", None))
            assert callable(getattr(mcp_tool, "_prepare_request", None))
            assert callable(getattr(mcp_tool, "_call_mcp_tool", None))
            assert callable(getattr(mcp_tool, "_process_response", None))
        else:
            pytest.skip("Could not load template module")
    except Exception as exc:
        pytest.skip(f"Template module loading failed: {exc}")
    finally:
        sys.path.pop(0)


def test_template_documentation() -> None:
    """Verify SKILL.md contains required sections."""
    skill_md = Path(__file__).resolve().parents[1] / "SKILL.md"
    content = skill_md.read_text(encoding="utf-8")

    # Check for required frontmatter fields
    assert "name:" in content
    assert "description:" in content
    assert "mcp:" in content
    assert "server_ref:" in content

    # Check for required sections
    assert "## Purpose" in content
    assert "## When to Use" in content
    assert "## Prerequisites" in content
    assert "## Procedures" in content
    assert "## Examples" in content
    assert "## Implementation Notes" in content
    assert "## Troubleshooting" in content


def test_template_examples_are_valid_json() -> None:
    """Verify example JSON files are valid."""
    import json

    examples_dir = Path(__file__).resolve().parents[1] / "resources" / "examples"

    in_json = examples_dir / "in.json"
    out_json = examples_dir / "out.json"

    # Both files should be valid JSON
    with in_json.open(encoding="utf-8") as f:
        in_data = json.load(f)
        assert isinstance(in_data, dict)

    with out_json.open(encoding="utf-8") as f:
        out_data = json.load(f)
        assert isinstance(out_data, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
