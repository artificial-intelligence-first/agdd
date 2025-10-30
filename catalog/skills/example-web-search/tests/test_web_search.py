"""
Unit tests for example web search MCP tool.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_web_search_structure_exists() -> None:
    """Verify web search skill directory structure exists."""
    skill_dir = Path(__file__).resolve().parents[1]
    assert skill_dir.name == "example-web-search"

    # Check required files exist
    assert (skill_dir / "SKILL.md").exists()
    assert (skill_dir / "skill.yaml").exists()
    assert (skill_dir / "impl" / "mcp_tool.py").exists()
    assert (skill_dir / "resources" / "examples" / "in.json").exists()
    assert (skill_dir / "resources" / "examples" / "out.json").exists()
    assert (skill_dir / "tests" / "test_web_search.py").exists()


def test_web_search_imports() -> None:
    """Verify web search module can be imported."""
    import sys
    from pathlib import Path
    import inspect

    # Add impl directory to path
    impl_dir = Path(__file__).resolve().parents[1] / "impl"
    sys.path.insert(0, str(impl_dir.parent.parent.parent))

    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("mcp_tool", impl_dir / "mcp_tool.py")
        if spec and spec.loader:
            mcp_tool = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mcp_tool)

            # Verify expected functions exist
            assert callable(getattr(mcp_tool, "run", None))
            assert callable(getattr(mcp_tool, "_validate", None))
            assert callable(getattr(mcp_tool, "_validate_url", None))
            assert callable(getattr(mcp_tool, "_fetch_url_via_mcp", None))
            assert callable(getattr(mcp_tool, "_extract_text_content", None))

            # Verify async functions
            assert inspect.iscoroutinefunction(mcp_tool.run)
            assert inspect.iscoroutinefunction(mcp_tool._fetch_url_via_mcp)
        else:
            pytest.fail("Could not load web search module")
    finally:
        sys.path.pop(0)


@pytest.mark.asyncio
async def test_web_search_run_basic() -> None:
    """Test basic web search execution with async."""
    import sys
    from pathlib import Path

    impl_dir = Path(__file__).resolve().parents[1] / "impl"
    sys.path.insert(0, str(impl_dir.parent.parent.parent))

    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("mcp_tool", impl_dir / "mcp_tool.py")
        if spec and spec.loader:
            mcp_tool = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mcp_tool)

            # Test with valid input (no MCP provided - should use mock)
            payload = {"url": "https://example.com", "extract_text": True}

            # Run function is now async
            result = await mcp_tool.run(payload)

            # Verify result structure
            assert isinstance(result, dict)
            assert "url" in result
            assert "success" in result
            assert result["url"] == "https://example.com"
            assert result["success"] is True

            # When no MCP is provided, should fall back to mock
            assert "Mock" in result.get("title", "")
        else:
            pytest.fail("Could not load web search module")
    finally:
        sys.path.pop(0)


def test_url_validation() -> None:
    """Test URL validation logic."""
    import sys
    from pathlib import Path

    impl_dir = Path(__file__).resolve().parents[1] / "impl"
    sys.path.insert(0, str(impl_dir.parent.parent.parent))

    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("mcp_tool", impl_dir / "mcp_tool.py")
        if spec and spec.loader:
            mcp_tool = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mcp_tool)

            # Valid URLs
            mcp_tool._validate_url("https://example.com")
            mcp_tool._validate_url("http://example.com")

            # Invalid URLs
            with pytest.raises(ValueError):
                mcp_tool._validate_url("")

            with pytest.raises(ValueError):
                mcp_tool._validate_url("not-a-url")

            with pytest.raises(ValueError):
                mcp_tool._validate_url("ftp://example.com")
        else:
            pytest.fail("Could not load web search module")
    finally:
        sys.path.pop(0)


def test_text_extraction() -> None:
    """Test HTML text extraction."""
    import sys
    from pathlib import Path

    impl_dir = Path(__file__).resolve().parents[1] / "impl"
    sys.path.insert(0, str(impl_dir.parent.parent.parent))

    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("mcp_tool", impl_dir / "mcp_tool.py")
        if spec and spec.loader:
            mcp_tool = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mcp_tool)

            html = """
            <html>
            <head><title>Test</title></head>
            <body>
                <script>alert('test');</script>
                <style>.test { color: red; }</style>
                <p>Hello World</p>
            </body>
            </html>
            """

            text = mcp_tool._extract_text_content(html)

            # Should extract text and remove script/style
            assert "Hello World" in text
            assert "alert" not in text
            assert "color: red" not in text
        else:
            pytest.fail("Could not load web search module")
    finally:
        sys.path.pop(0)


def test_web_search_examples_are_valid() -> None:
    """Verify example JSON files are valid."""
    examples_dir = Path(__file__).resolve().parents[1] / "resources" / "examples"

    in_json = examples_dir / "in.json"
    out_json = examples_dir / "out.json"

    # Both files should be valid JSON
    with in_json.open(encoding="utf-8") as f:
        in_data = json.load(f)
        assert isinstance(in_data, dict)
        assert "url" in in_data

    with out_json.open(encoding="utf-8") as f:
        out_data = json.load(f)
        assert isinstance(out_data, dict)
        assert "url" in out_data
        assert "success" in out_data


def test_web_search_documentation() -> None:
    """Verify SKILL.md contains required sections."""
    skill_md = Path(__file__).resolve().parents[1] / "SKILL.md"
    content = skill_md.read_text(encoding="utf-8")

    # Check for required frontmatter fields
    assert "name: example-web-search" in content
    assert 'server_ref: "fetch"' in content

    # Check for required sections
    assert "## Purpose" in content
    assert "## When to Use" in content
    assert "## Prerequisites" in content
    assert "## Examples" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
