"""GitHub webhook handling and response utilities for AGDD."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Iterable, Any

import httpx
from anyio import to_thread

from agdd.api.config import Settings
from agdd.api.run_tracker import find_new_run_id, snapshot_runs
from agdd.runners.agent_runner import invoke_mag

from .comment_parser import ParsedCommand, extract_from_code_blocks


logger = logging.getLogger(__name__)


async def _execute_commands(
    repo_full_name: str,
    issue_or_pr_number: int,
    commands: Iterable[ParsedCommand],
    settings: Settings,
) -> None:
    """Execute parsed commands and post results back to GitHub."""

    cmds = list(commands)
    if not cmds:
        return

    if not settings.GITHUB_TOKEN:
        logger.debug("Skipping GitHub command execution because AGDD_GITHUB_TOKEN is unset")
        return

    for cmd in cmds:
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

            response = format_success_comment(cmd.slug, run_id, output, settings.API_PREFIX)
        except Exception as exc:  # pragma: no cover - delegate to higher level logging
            response = format_error_comment(cmd.slug, exc)

        try:
            await post_comment(repo_full_name, issue_or_pr_number, response, settings.GITHUB_TOKEN)
        except Exception as exc:  # pragma: no cover - network and GitHub availability dependent
            logger.warning(
                "Failed to post GitHub comment for %s#%s via agent %s: %s",
                repo_full_name,
                issue_or_pr_number,
                cmd.slug,
                exc,
            )


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


def format_success_comment(
    slug: str, run_id: str | None, output: dict[str, Any], api_prefix: str
) -> str:
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
        comment += "**Artifacts**:\n"
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

    await _execute_commands(
        repo,
        issue_number,
        extract_from_code_blocks(comment_body),
        settings,
    )


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

    await _execute_commands(
        repo,
        pr_number,
        extract_from_code_blocks(comment_body),
        settings,
    )


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

    await _execute_commands(
        repo,
        pr_number,
        extract_from_code_blocks(pr_body),
        settings,
    )
