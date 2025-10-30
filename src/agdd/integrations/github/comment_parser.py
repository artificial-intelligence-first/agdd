"""GitHub comment parser for agent commands.

Extracts @agent-slug {json} commands from GitHub comments.
"""

from __future__ import annotations

import json
import re
from typing import Any, NamedTuple

# Pattern to match @agent-slug {json}
# Allows alphanumeric slugs with hyphens, JSON payload (including multiline)
# Use greedy matching to handle nested braces correctly
CMD_RE = re.compile(
    r"@(?P<agent>[a-z0-9][a-z0-9-]{1,63})\s+(?P<payload>\{(?:[^{}]|\{[^{}]*\})*\})",
    re.MULTILINE,
)


class ParsedCommand(NamedTuple):
    """Parsed agent command from comment."""

    slug: str
    payload: dict[str, Any]


def parse_comment(text: str) -> list[ParsedCommand]:
    """
    Parse GitHub comment text to extract agent commands.

    Format: @agent-slug {json_payload}

    Args:
        text: Comment body text

    Returns:
        List of parsed commands (may be empty)

    Example:
        >>> parse_comment("@my-agent {\"foo\": \"bar\"}")
        [ParsedCommand(slug='my-agent', payload={'foo': 'bar'})]
    """
    commands: list[ParsedCommand] = []

    for match in CMD_RE.finditer(text):
        slug = match.group("agent")
        payload_str = match.group("payload")

        try:
            payload = json.loads(payload_str)
            if not isinstance(payload, dict):
                # Skip non-dict payloads
                continue
            commands.append(ParsedCommand(slug=slug, payload=payload))
        except json.JSONDecodeError:
            # Skip invalid JSON
            continue

    return commands


def extract_from_code_blocks(text: str) -> list[ParsedCommand]:
    """
    Extract commands from markdown code blocks in addition to inline.

    Supports:
    ```json
    @agent-slug {
      "key": "value"
    }
    ```

    Args:
        text: Comment body text with potential code blocks

    Returns:
        List of parsed commands from both inline and code blocks
    """
    commands: list[ParsedCommand] = []
    seen_slugs: set[tuple[str, str]] = set()  # Track (slug, payload) to avoid duplicates

    # First, extract inline commands (outside code blocks)
    # Remove code blocks temporarily to avoid duplicates
    code_block_re = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.MULTILINE)
    text_without_blocks = code_block_re.sub("", text)

    for cmd in parse_comment(text_without_blocks):
        key = (cmd.slug, json.dumps(cmd.payload, sort_keys=True))
        if key not in seen_slugs:
            commands.append(cmd)
            seen_slugs.add(key)

    # Extract from code blocks
    for block_match in code_block_re.finditer(text):
        block_content = block_match.group(1)
        for cmd in parse_comment(block_content):
            key = (cmd.slug, json.dumps(cmd.payload, sort_keys=True))
            if key not in seen_slugs:
                commands.append(cmd)
                seen_slugs.add(key)

    return commands
