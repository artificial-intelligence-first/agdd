"""Tests for GitHub comment parser."""
from __future__ import annotations

from agdd.integrations.github.comment_parser import (
    extract_from_code_blocks,
    parse_comment,
)


def test_parse_simple_command() -> None:
    """Test parsing a simple inline command."""
    text = "@my-agent {\"foo\": \"bar\"}"
    commands = parse_comment(text)

    assert len(commands) == 1
    assert commands[0].slug == "my-agent"
    assert commands[0].payload == {"foo": "bar"}


def test_parse_multiline_command() -> None:
    """Test parsing a multiline JSON payload."""
    text = '''@test-agent {
        "key1": "value1",
        "key2": "value2"
    }'''
    commands = parse_comment(text)

    assert len(commands) == 1
    assert commands[0].slug == "test-agent"
    assert commands[0].payload == {"key1": "value1", "key2": "value2"}


def test_parse_multiple_commands() -> None:
    """Test parsing multiple commands in one comment."""
    text = '''
    Please run these agents:
    @agent-one {"input": "data1"}

    And also:
    @agent-two {"input": "data2"}
    '''
    commands = parse_comment(text)

    assert len(commands) == 2
    assert commands[0].slug == "agent-one"
    assert commands[0].payload == {"input": "data1"}
    assert commands[1].slug == "agent-two"
    assert commands[1].payload == {"input": "data2"}


def test_parse_command_with_hyphens() -> None:
    """Test parsing agent slug with hyphens."""
    text = "@offer-orchestrator-mag {\"foo\": 123}"
    commands = parse_comment(text)

    assert len(commands) == 1
    assert commands[0].slug == "offer-orchestrator-mag"
    assert commands[0].payload == {"foo": 123}


def test_parse_no_commands() -> None:
    """Test parsing text without commands."""
    text = "This is just a regular comment with no agent commands"
    commands = parse_comment(text)

    assert len(commands) == 0


def test_parse_invalid_json() -> None:
    """Test that invalid JSON is skipped."""
    text = "@my-agent {this is not json}"
    commands = parse_comment(text)

    assert len(commands) == 0


def test_parse_non_dict_json() -> None:
    """Test that non-dict JSON payloads are skipped."""
    text = "@my-agent [1, 2, 3]"
    commands = parse_comment(text)

    # Arrays are skipped, only dicts are accepted
    assert len(commands) == 0


def test_extract_from_code_blocks() -> None:
    """Test extracting commands from markdown code blocks."""
    text = '''
    Here's a command in a code block:

    ```json
    @test-agent {"value": 42}
    ```
    '''
    commands = extract_from_code_blocks(text)

    assert len(commands) == 1
    assert commands[0].slug == "test-agent"
    assert commands[0].payload == {"value": 42}


def test_extract_inline_and_code_blocks() -> None:
    """Test extracting commands from both inline and code blocks."""
    text = '''
    Inline command: @inline-agent {"type": "inline"}

    And in a code block:
    ```
    @block-agent {"type": "block"}
    ```
    '''
    commands = extract_from_code_blocks(text)

    # Should find both
    assert len(commands) == 2
    slugs = {cmd.slug for cmd in commands}
    assert "inline-agent" in slugs
    assert "block-agent" in slugs


def test_parse_complex_nested_json() -> None:
    """Test parsing nested JSON structures."""
    text = '''@complex-agent {
        "nested": {
            "key": "value",
            "array": [1, 2, 3]
        },
        "number": 123,
        "boolean": true
    }'''
    commands = parse_comment(text)

    assert len(commands) == 1
    assert commands[0].slug == "complex-agent"
    assert commands[0].payload["nested"]["key"] == "value"
    assert commands[0].payload["nested"]["array"] == [1, 2, 3]
    assert commands[0].payload["number"] == 123
    assert commands[0].payload["boolean"] is True
