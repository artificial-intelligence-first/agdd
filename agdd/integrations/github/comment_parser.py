"""Parse AGDD GitHub comment commands."""
from __future__ import annotations

import json
import re
from typing import Any, Iterator, NamedTuple


# Agent slugs are lowercase alphanumeric with hyphens (mirrors registry convention).
# The regex purposely stops right before the payload so that JSON decoding can
# handle arbitrarily nested structures.
_SLUG_PATTERN = re.compile(r"@(?P<agent>[a-z0-9][a-z0-9-]{1,63})\s*", re.MULTILINE)


class ParsedCommand(NamedTuple):
    """Parsed agent command from a GitHub comment."""

    slug: str
    payload: dict[str, Any]


def _iter_commands(text: str) -> Iterator[ParsedCommand]:
    """Yield ``ParsedCommand`` objects from ``text`` using JSON decoding."""

    decoder = json.JSONDecoder()
    position = 0
    length = len(text)

    while True:
        match = _SLUG_PATTERN.search(text, pos=position)
        if not match:
            break

        slug = match.group("agent")
        cursor = match.end()

        # Skip whitespace between the slug and JSON payload.
        while cursor < length and text[cursor].isspace():
            cursor += 1

        if cursor >= length or text[cursor] != "{":
            position = cursor
            continue

        try:
            payload, offset = decoder.raw_decode(text[cursor:])
        except json.JSONDecodeError:
            position = cursor + 1
            continue

        if isinstance(payload, dict):
            yield ParsedCommand(slug=slug, payload=payload)

        position = cursor + offset


def parse_comment(text: str) -> list[ParsedCommand]:
    """Parse GitHub comment text to extract agent commands."""

    return list(_iter_commands(text))


def extract_from_code_blocks(text: str) -> list[ParsedCommand]:
    """Extract commands from inline text and fenced code blocks."""

    commands: list[ParsedCommand] = []
    seen: set[tuple[str, str]] = set()

    # Remove fenced blocks temporarily to avoid double counting when parsing inline content.
    code_block_re = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.MULTILINE)
    inline_text = code_block_re.sub("", text)

    for cmd in _iter_commands(inline_text):
        fingerprint = (cmd.slug, json.dumps(cmd.payload, sort_keys=True))
        if fingerprint not in seen:
            seen.add(fingerprint)
            commands.append(cmd)

    for block in code_block_re.finditer(text):
        block_content = block.group(1)
        for cmd in _iter_commands(block_content):
            fingerprint = (cmd.slug, json.dumps(cmd.payload, sort_keys=True))
            if fingerprint not in seen:
                seen.add(fingerprint)
                commands.append(cmd)

    return commands
