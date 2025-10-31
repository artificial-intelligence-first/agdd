"""
Permission evaluator for tool execution governance.

Evaluates tool permissions based on policies defined in
catalog/policies/tool_permissions.yaml. Supports context-based
rules, environment overrides, and pattern matching.
"""

from __future__ import annotations

import fnmatch
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from agdd.core.permissions import ToolPermission

logger = logging.getLogger(__name__)


class PermissionEvaluatorError(Exception):
    """Base exception for permission evaluator errors."""

    pass


class PermissionEvaluator:
    """
    Permission evaluator for tool execution.

    Loads policy from YAML and evaluates permissions based on:
    - Tool-specific rules
    - Category-based defaults
    - Context-based rules
    - Environment overrides
    - Pattern matching
    """

    def __init__(
        self,
        policy_path: Optional[Path] = None,
        environment: Optional[str] = None,
    ):
        """
        Initialize permission evaluator.

        Args:
            policy_path: Path to policy YAML (default: catalog/policies/tool_permissions.yaml)
            environment: Environment name (development, staging, production)
        """
        self.policy_path = policy_path or Path("catalog/policies/tool_permissions.yaml")
        self.environment = environment or os.getenv("AGDD_ENVIRONMENT", "production")

        self.policy: Dict[str, Any] = {}
        self.load_policy()

    def load_policy(self) -> None:
        """Load policy from YAML file."""
        if not self.policy_path.exists():
            logger.warning(
                f"Policy file not found: {self.policy_path}, using defaults"
            )
            self.policy = self._get_default_policy()
            return

        try:
            with open(self.policy_path) as f:
                self.policy = yaml.safe_load(f) or {}

            logger.info(
                f"Loaded tool permissions policy from {self.policy_path} "
                f"(environment: {self.environment})"
            )

        except Exception as e:
            logger.error(f"Failed to load policy from {self.policy_path}: {e}")
            self.policy = self._get_default_policy()

    def _get_default_policy(self) -> Dict[str, Any]:
        """Get default policy (fallback if YAML not found)."""
        return {
            "default_permission": "REQUIRE_APPROVAL",
            "tools": {},
            "environments": {},
        }

    def evaluate(
        self,
        tool_name: str,
        context: Dict[str, Any],
    ) -> ToolPermission:
        """
        Evaluate permission for a tool execution.

        Args:
            tool_name: Tool name (e.g., "filesystem.write_file")
            context: Execution context (agent_slug, run_id, args, etc.)

        Returns:
            ToolPermission level (ALWAYS, REQUIRE_APPROVAL, NEVER)
        """
        # 1. Check tool-specific permissions
        tool_permission = self._check_tool_permission(tool_name)
        if tool_permission is not None:
            logger.debug(
                f"Tool {tool_name} has explicit permission: {tool_permission.value}"
            )
            return tool_permission

        # 2. Check context-based rules
        context_permission = self._check_context_rules(tool_name, context)
        if context_permission is not None:
            logger.debug(
                f"Tool {tool_name} matched context rule: {context_permission.value}"
            )
            return context_permission

        # 3. Check dangerous patterns
        pattern_permission = self._check_dangerous_patterns(tool_name)
        if pattern_permission is not None:
            logger.debug(
                f"Tool {tool_name} matched dangerous pattern: {pattern_permission.value}"
            )
            return pattern_permission

        # 4. Check category-based defaults
        category_permission = self._check_category_permission(tool_name)
        if category_permission is not None:
            logger.debug(
                f"Tool {tool_name} in category with permission: {category_permission.value}"
            )
            return category_permission

        # 5. Check environment-specific overrides
        env_permission = self._check_environment_override(tool_name)
        if env_permission is not None:
            logger.debug(
                f"Tool {tool_name} has environment override: {env_permission.value}"
            )
            return env_permission

        # 6. Fall back to default permission
        default_permission = self.policy.get("default_permission", "REQUIRE_APPROVAL")
        logger.debug(
            f"Tool {tool_name} using default permission: {default_permission}"
        )

        return ToolPermission(default_permission.lower())

    def _check_tool_permission(self, tool_name: str) -> Optional[ToolPermission]:
        """Check tool-specific permissions."""
        tools = self.policy.get("tools", {})
        tool_config = tools.get(tool_name)

        if tool_config is None:
            return None

        permission_str = tool_config.get("permission")
        if permission_str is None:
            return None

        return ToolPermission(permission_str.lower())

    def _check_category_permission(self, tool_name: str) -> Optional[ToolPermission]:
        """Check category-based permissions."""
        categories = self.policy.get("categories", {})

        for category_name, category_config in categories.items():
            tool_patterns = category_config.get("tools", [])

            for pattern in tool_patterns:
                if fnmatch.fnmatch(tool_name, pattern):
                    permission_str = category_config.get("permission")
                    if permission_str:
                        return ToolPermission(permission_str.lower())

        return None

    def _check_context_rules(
        self,
        tool_name: str,
        context: Dict[str, Any],
    ) -> Optional[ToolPermission]:
        """Check context-based rules."""
        context_rules = self.policy.get("context_rules", [])

        for rule in context_rules:
            if self._matches_context_rule(tool_name, context, rule):
                permission_str = rule.get("permission")
                if permission_str:
                    logger.info(
                        f"Tool {tool_name} matched context rule: {rule.get('name')}"
                    )
                    return ToolPermission(permission_str.lower())

        return None

    def _matches_context_rule(
        self,
        tool_name: str,
        context: Dict[str, Any],
        rule: Dict[str, Any],
    ) -> bool:
        """Check if a tool matches a context rule."""
        condition = rule.get("condition", {})

        # Check exact tool match
        if "tool" in condition:
            if condition["tool"] != tool_name:
                return False

        # Check tool pattern match
        if "tool_pattern" in condition:
            if not fnmatch.fnmatch(tool_name, condition["tool_pattern"]):
                return False

        # Check args match
        if "args_match" in condition:
            tool_args = context.get("tool_args", {})
            if not self._matches_args(tool_args, condition["args_match"]):
                return False

        # Check context match
        if "context_match" in condition:
            if not self._matches_dict(context, condition["context_match"]):
                return False

        return True

    def _matches_args(
        self,
        args: Dict[str, Any],
        patterns: Dict[str, Any],
    ) -> bool:
        """Check if arguments match patterns."""
        for key, pattern in patterns.items():
            if key not in args:
                return False

            value = args[key]

            # Handle special comparisons
            if isinstance(pattern, dict):
                if "less_than" in pattern:
                    if not (isinstance(value, (int, float)) and value < pattern["less_than"]):
                        return False
                if "greater_than" in pattern:
                    if not (isinstance(value, (int, float)) and value > pattern["greater_than"]):
                        return False
                continue

            # Handle wildcard pattern matching for strings
            if isinstance(pattern, str) and isinstance(value, str):
                if not fnmatch.fnmatch(value, pattern):
                    return False
            else:
                # Exact match
                if value != pattern:
                    return False

        return True

    def _matches_dict(
        self,
        data: Dict[str, Any],
        patterns: Dict[str, Any],
    ) -> bool:
        """Check if dictionary matches patterns."""
        for key, pattern in patterns.items():
            if key not in data:
                return False

            value = data[key]

            # Handle wildcard pattern matching for strings
            if isinstance(pattern, str) and isinstance(value, str):
                if not fnmatch.fnmatch(value, pattern):
                    return False
            else:
                # Exact match
                if value != pattern:
                    return False

        return True

    def _check_dangerous_patterns(self, tool_name: str) -> Optional[ToolPermission]:
        """Check dangerous operation patterns."""
        dangerous_patterns = self.policy.get("dangerous_patterns", [])

        for pattern_config in dangerous_patterns:
            pattern = pattern_config.get("pattern")
            if pattern and fnmatch.fnmatch(tool_name, pattern):
                permission_str = pattern_config.get("permission")
                if permission_str:
                    logger.warning(
                        f"Tool {tool_name} matched dangerous pattern: {pattern}"
                    )
                    return ToolPermission(permission_str.lower())

        return None

    def _check_environment_override(self, tool_name: str) -> Optional[ToolPermission]:
        """Check environment-specific overrides."""
        environments = self.policy.get("environments", {})
        env_config = environments.get(self.environment)

        if env_config is None:
            return None

        # Check environment-specific tool overrides
        overrides = env_config.get("overrides", {})

        # First check exact match
        if tool_name in overrides:
            permission_str = overrides[tool_name]
            return ToolPermission(permission_str.lower())

        # Then check pattern match
        for pattern, permission_str in overrides.items():
            if fnmatch.fnmatch(tool_name, pattern):
                return ToolPermission(permission_str.lower())

        # Finally check environment default
        env_default = env_config.get("default_permission")
        if env_default:
            return ToolPermission(env_default.lower())

        return None

    def get_tool_metadata(self, tool_name: str) -> Dict[str, Any]:
        """
        Get metadata for a tool (description, category, etc.).

        Args:
            tool_name: Tool name

        Returns:
            Tool metadata dictionary
        """
        tools = self.policy.get("tools", {})
        tool_config = tools.get(tool_name, {})

        metadata = {
            "tool_name": tool_name,
            "description": tool_config.get("description", ""),
            "permission": self.evaluate(tool_name, {}).value,
        }

        return metadata

    def list_allowed_tools(
        self,
        context: Optional[Dict[str, Any]] = None,
    ) -> list[str]:
        """
        List all tools with ALWAYS permission.

        Args:
            context: Optional context for evaluation

        Returns:
            List of tool names
        """
        context = context or {}
        allowed_tools = []

        # Get all explicitly configured tools
        tools = self.policy.get("tools", {})
        for tool_name in tools:
            if self.evaluate(tool_name, context) == ToolPermission.ALWAYS:
                allowed_tools.append(tool_name)

        return allowed_tools
