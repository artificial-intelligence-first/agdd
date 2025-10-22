"""Process GitHub webhook events and execute AGDD agents on demand."""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Iterable

import httpx
from anyio import to_thread

from agdd.api.config import Settings
from agdd.api.run_tracker import find_new_run_id, snapshot_runs
from agdd.runners.agent_runner import invoke_mag

from .comment_parser import ParsedCommand, extract_from_code_blocks


logger = logging.getLogger(__name__)


async def post_comment(
    repo_full_name: str,
    issue_number: int,
    body: str,
    token: str,
) -> None:
    """
    Post a comment to a GitHub issue or PR.

    Args:
        repo_full_name: Repository in format "owner/repo"
        issue_number: Issue or PR number
        body: Comment body (markdown)
        token: GitHub API token

    Raises:
        httpx.HTTPError: If API request fails
    """
    url = f"https://api.github.com/repos/{repo_full_name}/issues/{issue_number}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            headers=headers,
            json={"body": body},
            timeout=30.0,
        )
        response.raise_for_status()


def format_success_comment(slug: str, run_id: str | None, output: dict[str, Any], api_prefix: str) -> str:
    """
    Format successful agent execution result as GitHub comment.

    Args:
        slug: Agent slug
        run_id: Run identifier (may be None)
        output: Agent output
        api_prefix: API URL prefix for artifacts

    Returns:
        Formatted markdown comment
    """
    # Truncate output for display
    output_str = str(output)
    if len(output_str) > 1500:
        output_str = output_str[:1500] + "\n... (truncated)"

    comment = f"✅ **AGDD Agent `{slug}` execution completed**\n\n"

    if run_id:
        comment += f"**Run ID**: `{run_id}`\n\n"
        comment += f"**Artifacts**:\n"
        comment += f"- Summary: `GET {api_prefix}/runs/{run_id}`\n"
        comment += f"- Logs: `GET {api_prefix}/runs/{run_id}/logs`\n\n"

    comment += f"**Output** (truncated):\n```json\n{output_str}\n```\n"

    return comment


def format_error_comment(slug: str, error: Exception) -> str:
    """
    Format agent execution error as GitHub comment.

    Args:
        slug: Agent slug that failed
        error: Exception that occurred

    Returns:
        Formatted markdown comment
    """
    error_type = type(error).__name__
    error_msg = str(error)

    comment = f"❌ **AGDD Agent `{slug}` execution failed**\n\n"
    comment += f"**Error**: `{error_type}`\n\n"
    comment += f"```\n{error_msg}\n```\n\n"
    comment += "**Troubleshooting**:\n"
    comment += "- Verify the agent slug exists in `registry/agents.yaml`\n"
    comment += "- Check that the JSON payload matches the agent's input schema\n"
    comment += "- Review agent implementation for runtime errors\n"

    return comment


async def _execute_command_and_format_response(
    cmd: ParsedCommand, settings: Settings
) -> str:
    """Execute an agent command and format the GitHub comment response."""

    base = Path(settings.RUNS_BASE_DIR)
    before = snapshot_runs(base)
    started_at = time.time()

    try:
        output = await to_thread.run_sync(invoke_mag, cmd.slug, cmd.payload, base)

        run_id: str | None = None
        if isinstance(output, dict):
            run_id = output.get("run_id")
        if run_id is None:
            run_id = find_new_run_id(base, before, cmd.slug, started_at)

        if run_id:
            logger.info(
                "GitHub command executed successfully", extra={"slug": cmd.slug, "run_id": run_id}
            )
        else:
            logger.info("GitHub command executed without run_id", extra={"slug": cmd.slug})

        return format_success_comment(cmd.slug, run_id, output, settings.API_PREFIX)
    except Exception as exc:  # noqa: BLE001 - propagate via formatted response
        logger.exception("GitHub command for %s failed", cmd.slug)
        return format_error_comment(cmd.slug, exc)


async def _run_commands_and_comment(
    commands: Iterable[ParsedCommand],
    repo_full_name: str,
    issue_number: int,
    settings: Settings,
) -> None:
    """Execute parsed commands and post the results back to GitHub."""

    if not settings.GITHUB_TOKEN:
        logger.debug("Skipping GitHub response posting because GITHUB_TOKEN is not configured")
        return

    command_list = list(commands)
    if not command_list:
        return

    for cmd in command_list:
        response = await _execute_command_and_format_response(cmd, settings)
        try:
            await post_comment(repo_full_name, issue_number, response, settings.GITHUB_TOKEN)
        except Exception as exc:  # noqa: BLE001 - webhook should not fail hard
            logger.warning(
                "Failed to post GitHub response comment for %s: %s", cmd.slug, exc
            )


async def handle_issue_comment(event: dict[str, Any], settings: Settings) -> None:
    """
    Handle issue_comment webhook event.

    Extracts commands from comment body, executes agents, and posts results.

    Args:
        event: GitHub webhook event payload
        settings: API settings
    """
    # Extract event data
    action = event.get("action")
    if action not in ["created", "edited"]:
        return  # Only process new/edited comments

    repo = event["repository"]["full_name"]
    issue_number = event["issue"]["number"]
    comment_body = event["comment"]["body"]

    # Parse commands from comment
    commands = extract_from_code_blocks(comment_body)
    await _run_commands_and_comment(commands, repo, issue_number, settings)


async def handle_pull_request_review_comment(event: dict[str, Any], settings: Settings) -> None:
    """
    Handle pull_request_review_comment webhook event.

    Similar to issue comments, but for PR review comments.

    Args:
        event: GitHub webhook event payload
        settings: API settings
    """
    action = event.get("action")
    if action not in ["created", "edited"]:
        return

    repo = event["repository"]["full_name"]
    pr_number = event["pull_request"]["number"]
    comment_body = event["comment"]["body"]

    # Parse commands
    commands = extract_from_code_blocks(comment_body)
    await _run_commands_and_comment(commands, repo, pr_number, settings)


async def handle_pull_request(event: dict[str, Any], settings: Settings) -> None:
    """
    Handle pull_request webhook event.

    Checks PR description for commands (similar to comments).

    Args:
        event: GitHub webhook event payload
        settings: API settings
    """
    action = event.get("action")
    if action not in ["opened", "edited", "synchronize"]:
        return

    repo = event["repository"]["full_name"]
    pr_number = event["pull_request"]["number"]
    pr_body = event["pull_request"].get("body", "")

    # Parse commands from PR body
    commands = extract_from_code_blocks(pr_body)
    await _run_commands_and_comment(commands, repo, pr_number, settings)
