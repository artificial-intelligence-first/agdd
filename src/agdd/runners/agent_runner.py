"""
Agent Runner - Orchestrates MAG and SAG execution with observability.

Provides invoke_mag() and invoke_sag() interfaces for agent invocation,
dependency resolution, and metrics collection.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, Mapping, Optional

import yaml

from agdd.evaluation.runtime import EvalRuntime
from agdd.mcp import MCPRegistry, MCPRuntime
from agdd.observability.logger import ObservabilityLogger
from agdd.registry import AgentDescriptor, Registry, get_registry
from agdd.router import ExecutionPlan, Router, get_router
from agdd.routing.router import Plan as LLMPlan, get_plan as get_llm_plan

logger = logging.getLogger(__name__)

# Milliseconds per second for duration calculations
MS_PER_SECOND = 1000


def _env_flag(name: str, default: bool) -> bool:
    """Read a boolean feature flag from environment variables."""

    raw = os.getenv(name)
    if raw is None:
        return default

    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


AgentCallable = Callable[..., Dict[str, Any]]
SkillCallable = Callable[[Dict[str, Any]], Dict[str, Any]]


def _is_async_callable(fn: Any) -> bool:
    """
    Check if a callable is async (coroutine function).

    This handles multiple patterns for async callables:
    - Regular async functions: async def foo()
    - Async callable objects: class Foo with async def __call__()
    - functools.partial wrappers around async functions

    Args:
        fn: Callable to check

    Returns:
        True if callable is async, False otherwise
    """
    # Check if fn itself is a coroutine function
    if inspect.iscoroutinefunction(fn):
        return True

    # Unwrap functools.partial to check the underlying function
    if isinstance(fn, functools.partial):
        return _is_async_callable(fn.func)

    # Check if fn has an async __call__ method
    if hasattr(fn, "__call__"):
        call_method = getattr(fn, "__call__", None)
        if call_method and inspect.iscoroutinefunction(call_method):
            return True

    return False


@dataclass
class Delegation:
    """Request to delegate work to a sub-agent."""

    task_id: str
    sag_id: str  # Sub-agent slug
    input: Dict[str, Any]
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Result:
    """Result from agent execution."""

    task_id: str
    status: str  # "success", "failure", "partial"
    output: Dict[str, Any]
    metrics: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class _ExecutionContext:
    """Container with execution artefacts shared across MAG/SAG invocations."""

    agent: AgentDescriptor
    execution_plan: ExecutionPlan
    plan_snapshot: dict[str, Any]
    llm_plan: LLMPlan
    observer: ObservabilityLogger


class SkillRuntime:
    """Skill execution runtime - delegates to skill implementations"""

    def __init__(
        self,
        registry: Optional[Registry] = None,
        enable_mcp: Optional[bool] = None,
    ):
        self.registry = registry or get_registry()
        if enable_mcp is None:
            enable_mcp = _env_flag("AGDD_ENABLE_MCP", True)
        self.enable_mcp = enable_mcp
        self.mcp_registry: Optional[MCPRegistry] = None
        self._mcp_started = False

    def exists(self, skill_id: str) -> bool:
        """Check if skill exists in registry"""
        try:
            self.registry.load_skill(skill_id)
            return True
        except (FileNotFoundError, ValueError):
            return False

    async def _ensure_mcp_started(self) -> None:
        """
        Lazily initialize and start MCP servers on first use.

        If server startup fails, logs a warning and continues without MCP.
        This allows skills with optional MCP support (graceful fallback)
        to execute with mcp=None instead of failing outright.
        """
        if not self.enable_mcp:
            return

        if self._mcp_started:
            return

        # Allow tests or callers to inject a preconfigured registry.
        # When present we still need to ensure servers are running.
        if self.mcp_registry is not None:
            logger.info("Using preconfigured MCP registry (starting servers if needed)")
            try:
                await self.mcp_registry.start_all_servers()
                self._mcp_started = True
                logger.info("MCP servers started on injected registry")
            except Exception as exc:  # pragma: no cover - defensive guard
                logger.warning(
                    "Failed to start MCP servers on injected registry: %s. "
                    "Skills with MCP support will execute with mcp=None (graceful fallback).",
                    exc,
                )
                self._mcp_started = False
            return

        logger.info("Initializing MCP registry and starting servers")
        try:
            self.mcp_registry = MCPRegistry()
            self.mcp_registry.discover_servers()
            await self.mcp_registry.start_all_servers()
            self._mcp_started = True
            logger.info(f"MCP servers started: {self.mcp_registry.list_running_servers()}")
        except Exception as e:
            logger.warning(
                f"Failed to start MCP servers: {e}. "
                "Skills with MCP support will execute with mcp=None (graceful fallback)."
            )
            # Keep _mcp_started = False so skills receive mcp=None
            self.mcp_registry = None

    async def _cleanup_mcp(self) -> None:
        """Stop all MCP servers and cleanup resources."""
        if self.mcp_registry and self._mcp_started:
            logger.info("Stopping MCP servers")
            await self.mcp_registry.stop_all_servers()
            self._mcp_started = False

    def _create_mcp_runtime(self, skill_id: str) -> Optional[MCPRuntime]:
        """Create MCP runtime for a skill with its declared permissions.

        Args:
            skill_id: Skill identifier to load permissions for

        Returns:
            MCPRuntime with granted permissions, or None if MCP not enabled
        """
        if not self.enable_mcp or not self.mcp_registry:
            return None

        try:
            skill_desc = self.registry.load_skill(skill_id)
            mcp_permissions = [perm for perm in skill_desc.permissions if perm.startswith("mcp:")]

            if not mcp_permissions:
                return None

            runtime = MCPRuntime(self.mcp_registry)
            runtime.grant_permissions(mcp_permissions)
            logger.debug(
                f"Created MCP runtime for skill '{skill_id}' with permissions: {mcp_permissions}"
            )
            return runtime

        except Exception as e:
            logger.warning(f"Failed to create MCP runtime for skill '{skill_id}': {e}")
            return None

    async def invoke_async(
        self, skill_id: str, payload: Dict[str, Any], _auto_cleanup: bool = False
    ) -> Dict[str, Any]:
        """Execute a skill asynchronously with MCP support.

        Supports two types of skills:
        1. Async skills with MCP parameter
        2. Async skills without MCP

        Args:
            skill_id: Skill identifier
            payload: Input payload for skill
            _auto_cleanup: If True, cleanup MCP servers after execution.
                          Used by sync wrapper to ensure cleanup in same event loop.

        Returns:
            Skill execution result
        """
        skill_desc = self.registry.load_skill(skill_id)
        callable_fn = self.registry.resolve_entrypoint(skill_desc.entrypoint)

        # Inspect skill signature to detect MCP parameter
        sig = inspect.signature(callable_fn)
        has_mcp_param = "mcp" in sig.parameters
        is_async = _is_async_callable(callable_fn)

        mcp_runtime: Optional[MCPRuntime] = None
        mcp_started_here = False

        # If skill expects MCP, ensure servers are started and create runtime
        if has_mcp_param and self.enable_mcp:
            if not self._mcp_started:
                mcp_started_here = True
            await self._ensure_mcp_started()
            mcp_runtime = self._create_mcp_runtime(skill_id)

        try:
            if not is_async:
                raise ValueError(
                    f"Skill '{skill_id}' must be async. Synchronous skills are not supported."
                )

            # Async skill
            if has_mcp_param:
                logger.debug(f"Invoking async skill '{skill_id}' with MCP")
                result = await callable_fn(payload, mcp=mcp_runtime)
            else:
                logger.debug(f"Invoking async skill '{skill_id}' without MCP")
                result = await callable_fn(payload)

            return result  # type: ignore[no-any-return]

        except Exception as e:
            logger.error(f"Skill '{skill_id}' execution failed: {e}", exc_info=True)
            raise
        finally:
            # Cleanup MCP if we started it here and auto_cleanup is requested
            # This ensures sync wrappers cleanup in the same event loop
            if _auto_cleanup and mcp_started_here and self._mcp_started:
                try:
                    await self._cleanup_mcp()
                except Exception as cleanup_error:
                    logger.warning(f"MCP cleanup in invoke_async failed: {cleanup_error}")

    def invoke(self, skill_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a skill and return result (sync wrapper for invoke_async).

        This method handles async/sync context automatically:
        - If called from async context, runs invoke_async directly
        - If called from sync context, creates event loop to run invoke_async

        Note: When called from sync context, MCP servers are automatically
        cleaned up in the same event loop to prevent process leaks.

        Args:
            skill_id: Skill identifier
            payload: Input payload for skill

        Returns:
            Skill execution result
        """
        # Try to get running event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No event loop running, create one
            loop = None

        if loop is not None:
            # We're in an async context, but invoke() is sync
            # This shouldn't happen in normal usage, but handle it
            logger.warning(
                f"invoke() called from async context for skill '{skill_id}'. "
                "Consider using invoke_async() directly."
            )
            # We can't use await here, so we need to create a task
            # However, this is tricky. Let's just run it in the current loop.
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run, self.invoke_async(skill_id, payload, _auto_cleanup=True)
                )
                try:
                    result = future.result()
                    return result
                finally:
                    # Give MCP subprocess cleanup time to complete
                    time.sleep(0.5)
        else:
            # No event loop, create one and run with auto cleanup
            try:
                result = asyncio.run(self.invoke_async(skill_id, payload, _auto_cleanup=True))
                return result
            finally:
                # Give MCP subprocess cleanup time to complete
                time.sleep(0.5)


class AgentRunner:
    """Runner for MAG and SAG agents with execution planning and cost tracking"""

    def __init__(
        self,
        registry: Optional[Registry] = None,
        base_dir: Optional[Path] = None,
        router: Optional[Router] = None,
        enable_mcp: Optional[bool] = None,
    ):
        self.registry: Registry = registry or get_registry()
        self.base_dir = base_dir
        if enable_mcp is None:
            enable_mcp = _env_flag("AGDD_ENABLE_MCP", True)
        self.enable_mcp = enable_mcp
        self.skills = SkillRuntime(registry=self.registry, enable_mcp=self.enable_mcp)
        self.evals = EvalRuntime(registry=self.registry)
        self.router: Router = router or get_router()
        self._task_index: dict[str, list[str]] | None = None

    def _load_task_index(self) -> dict[str, list[str]]:
        if self._task_index is None:
            self._task_index = self._build_task_index()
        return self._task_index

    def _build_task_index(self) -> dict[str, list[str]]:
        index: dict[str, list[str]] = {}
        registry_path = self.registry.base_path / "catalog" / "registry" / "agents.yaml"
        if not registry_path.exists():
            return index

        with open(registry_path, "r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}

        tasks = raw.get("tasks", [])
        if not isinstance(tasks, list):
            return index

        for task in tasks:
            if not isinstance(task, Mapping):
                continue
            target_slugs: list[str] = []
            for ref_key in ("default", "main_agent"):
                slug = Registry._normalize_agent_ref(task.get(ref_key))
                if slug:
                    target_slugs.append(slug)
            if not target_slugs:
                continue

            task_id = task.get("id")
            if not isinstance(task_id, str) or not task_id:
                continue

            for slug in target_slugs:
                bucket = index.setdefault(slug, [])
                if task_id not in bucket:
                    bucket.append(task_id)

        return index

    async def _cleanup_mcp_async(self) -> None:
        """
        Cleanup MCP resources in async context (same event loop).

        This should be called from async code paths to ensure MCP servers
        are stopped in the same event loop where they were started.
        """
        if self.enable_mcp and self.skills._mcp_started:
            try:
                await self.skills._cleanup_mcp()
            except Exception as e:
                logger.warning(f"MCP cleanup failed: {e}")

    def _serialize_execution_plan(self, plan: ExecutionPlan) -> dict[str, Any]:
        return {
            "agent_slug": plan.agent_slug,
            "task_type": plan.task_type,
            "provider_hint": plan.provider_hint,
            "resource_tier": plan.resource_tier,
            "estimated_duration": plan.estimated_duration,
            "timeout_ms": plan.timeout_ms,
            "token_budget": plan.token_budget,
            "time_budget_s": plan.time_budget_s,
            "enable_otel": plan.enable_otel,
            "span_context": dict(plan.span_context),
            "metadata": dict(plan.metadata),
        }

    def _determine_task_type(self, agent: AgentDescriptor, context: Dict[str, Any]) -> str:
        task_type = context.get("task_type")
        if isinstance(task_type, str) and task_type:
            return task_type

        task_index = self._load_task_index()
        candidate_tasks = task_index.get(agent.slug)
        if candidate_tasks:
            return candidate_tasks[0]

        provider_config = agent.raw.get("provider_config", {})
        if isinstance(provider_config, Mapping):
            cfg_task = provider_config.get("task_type")
            if isinstance(cfg_task, str) and cfg_task:
                return cfg_task

        return agent.slug

    def _extract_llm_overrides(
        self,
        agent: AgentDescriptor,
        context: Dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        overrides: dict[str, Any] = {}
        candidate_sources: list[Any] = []

        context_override = context.get("llm_overrides") or context.get("plan_overrides")
        if context_override:
            candidate_sources.append(context_override)

        provider_config = agent.raw.get("provider_config", {})
        if isinstance(provider_config, Mapping):
            config_override = provider_config.get("llm_overrides")
            if config_override:
                candidate_sources.append(config_override)

        allowed_keys = {
            "provider",
            "model",
            "use_batch",
            "use_cache",
            "structured_output",
            "moderation",
            "metadata",
        }

        for source in candidate_sources:
            if not isinstance(source, Mapping):
                continue
            for key, value in source.items():
                if key in allowed_keys:
                    overrides[key] = value

        return overrides or None

    def _build_default_llm_plan(
        self,
        task_type: str,
        agent: AgentDescriptor,
        agent_plan_snapshot: dict[str, Any],
    ) -> LLMPlan:
        provider_config = agent.raw.get("provider_config", {})
        provider_hint: Optional[str] = None
        default_model: Optional[str] = None

        if isinstance(provider_config, Mapping):
            provider_hint = provider_config.get("provider_hint")
            default_model = provider_config.get("model")

        provider_name = provider_hint or agent_plan_snapshot.get("provider_hint") or "local"
        metadata = dict(agent_plan_snapshot.get("metadata", {}))
        metadata.setdefault("source", "fallback")
        model_name = metadata.get("model") or default_model or "unknown"

        return LLMPlan(
            task_type=task_type,
            provider=str(provider_name),
            model=str(model_name),
            use_batch=False,
            use_cache=False,
            structured_output=False,
            moderation=False,
            metadata=metadata,
        )

    def _resolve_llm_plan(
        self,
        agent: AgentDescriptor,
        context: Dict[str, Any],
        agent_plan_snapshot: dict[str, Any],
    ) -> LLMPlan:
        task_type = self._determine_task_type(agent, context)
        overrides = self._extract_llm_overrides(agent, context)
        plan = get_llm_plan(task_type, overrides=overrides)
        if plan is None:
            logger.debug("No routing plan found for task '%s'; using fallback.", task_type)
            return self._build_default_llm_plan(task_type, agent, agent_plan_snapshot)
        return plan

    def _plan_summary(self, execution_plan: ExecutionPlan, llm_plan: LLMPlan) -> dict[str, Any]:
        """Summarize execution and LLM plan details for logging."""
        return {
            "task_type": execution_plan.task_type,
            "provider_hint": execution_plan.provider_hint,
            "timeout_ms": execution_plan.timeout_ms,
            "token_budget": execution_plan.token_budget,
            "use_batch": llm_plan.use_batch,
            "use_cache": llm_plan.use_cache,
            "structured_output": llm_plan.structured_output,
            "moderation": llm_plan.moderation,
        }

    def _prepare_execution(
        self,
        slug: str,
        run_id: str,
        context: Optional[Dict[str, Any]],
    ) -> _ExecutionContext:
        """Load agent, compute plans, and create an observability logger."""
        import copy

        effective_context: Dict[str, Any] = context or {}

        # Load agent from registry (may be cached)
        cached_agent = self.registry.load_agent(slug)

        # Apply deterministic settings if deterministic mode is enabled
        # Create a copy to avoid mutating the cached agent descriptor
        if effective_context.get("deterministic"):
            try:
                from agdd.runner_determinism import (
                    apply_deterministic_settings,
                    get_deterministic_mode,
                    set_deterministic_mode,
                )

                # Save current deterministic mode state
                previous_mode = get_deterministic_mode()

                # Temporarily enable deterministic mode for settings application
                # This ensures apply_deterministic_settings() actually applies settings
                if not previous_mode:
                    set_deterministic_mode(True)

                try:
                    # Create a shallow copy of the agent descriptor to avoid mutating the cache
                    agent = copy.copy(cached_agent)
                    # Deep copy the raw dict to avoid mutating nested structures
                    agent.raw = copy.deepcopy(cached_agent.raw)

                    # Get the provider config from agent definition
                    provider_config = agent.raw.get("provider_config", {})

                    # Apply deterministic settings (returns a copy)
                    deterministic_config = apply_deterministic_settings(provider_config)

                    # Update the COPY's raw config with deterministic settings
                    # This affects the execution plan and LLM plan creation
                    agent.raw["provider_config"] = deterministic_config
                finally:
                    # Restore previous deterministic mode if we changed it
                    # This prevents leaking deterministic state to other runs
                    if not previous_mode:
                        set_deterministic_mode(False)
            except ImportError:
                # Gracefully handle if runner_determinism module isn't available
                logger.warning("Could not import runner_determinism module; skipping deterministic settings")
                agent = cached_agent
        else:
            # Non-deterministic run: use cached agent as-is
            agent = cached_agent

        execution_plan = self.router.get_plan(agent, effective_context)
        plan_snapshot = self._serialize_execution_plan(execution_plan)
        llm_plan = self._resolve_llm_plan(agent, effective_context, plan_snapshot)

        parent_span_id = effective_context.get("parent_span_id") or execution_plan.span_context.get(
            "parent_span_id"
        )

        # Extract determinism information from context
        deterministic = effective_context.get("deterministic")
        replay_mode = effective_context.get("replay_mode")
        environment_snapshot = effective_context.get("environment_snapshot")

        observer = ObservabilityLogger(
            run_id,
            slug=slug,
            base_dir=self.base_dir,
            agent_plan=plan_snapshot,
            llm_plan=llm_plan,
            enable_otel=execution_plan.enable_otel,
            parent_span_id=parent_span_id,
            deterministic=deterministic,
            replay_mode=replay_mode,
            environment_snapshot=environment_snapshot,
        )

        return _ExecutionContext(
            agent=agent,
            execution_plan=execution_plan,
            plan_snapshot=plan_snapshot,
            llm_plan=llm_plan,
            observer=observer,
        )

    def _record_placeholder_cost(
        self,
        ctx: _ExecutionContext,
        *,
        step: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record placeholder cost entries for observability consistency."""
        ctx.observer.record_cost(
            0.0,
            0,
            model=ctx.llm_plan.model if ctx.llm_plan else None,
            provider=ctx.llm_plan.provider if ctx.llm_plan else None,
            metadata=metadata,
            step=step,
        )

    async def _execute_mag_async(
        self,
        exec_ctx: _ExecutionContext,
        payload: Dict[str, Any],
    ) -> tuple[Dict[str, Any], int]:
        """
        Execute the MAG agent asynchronously and return output with duration.

        Args:
            exec_ctx: Execution context
            payload: Input payload for agent

        Returns:
            Tuple of (output, duration_ms)
        """
        try:
            run_fn = self.registry.resolve_entrypoint(exec_ctx.agent.entrypoint)
            t0 = time.time()
            output: Dict[str, Any] = await run_fn(
                payload,
                registry=self.registry,
                skills=self.skills,
                runner=self,  # Allow MAG to delegate to SAG
                obs=exec_ctx.observer,
            )
            duration_ms = int((time.time() - t0) * MS_PER_SECOND)
            return output, duration_ms
        finally:
            await self._cleanup_mcp_async()

    def _execute_mag(
        self,
        exec_ctx: _ExecutionContext,
        payload: Dict[str, Any],
    ) -> tuple[Dict[str, Any], int]:
        """
        Execute the MAG agent and return output with duration.

        Automatically detects async agents and runs them appropriately.

        Args:
            exec_ctx: Execution context
            payload: Input payload for agent

        Returns:
            Tuple of (output, duration_ms)
        """
        run_fn = self.registry.resolve_entrypoint(exec_ctx.agent.entrypoint)

        # Check if agent is async (handles async def, async __call__, and partials)
        if not _is_async_callable(run_fn):
            raise ValueError(
                f"Agent '{exec_ctx.agent.slug}' must be async. Synchronous agents are not supported."
            )

        logger.debug(f"Agent '{exec_ctx.agent.slug}' is async, using async execution")
        return self._run_async_safely(self._execute_mag_async(exec_ctx, payload))  # type: ignore[no-any-return]

    def _finalize_mag_success(
        self,
        exec_ctx: _ExecutionContext,
        duration_ms: int,
    ) -> None:
        """
        Finalize successful MAG execution with metrics and logging.

        Args:
            exec_ctx: Execution context
            duration_ms: Execution duration in milliseconds
        """
        obs = exec_ctx.observer
        obs.metric("duration_ms", duration_ms)
        self._record_placeholder_cost(exec_ctx, step="mag", metadata={"stage": "mag"})
        obs.log(
            "end",
            {
                "status": "success",
                "duration_ms": duration_ms,
                "cost_usd": obs.cost_usd,
                "tokens": obs.token_count,
                "llm_plan": obs.llm_plan_snapshot,
            },
        )
        obs.finalize()

    def _handle_mag_error(
        self,
        exec_ctx: Optional[_ExecutionContext],
        error: Exception,
    ) -> None:
        """
        Handle MAG execution error with logging and cost tracking.

        Args:
            exec_ctx: Execution context (may be None if error occurred early)
            error: Exception that occurred
        """
        if exec_ctx is not None:
            exec_ctx.observer.log("error", {"error": str(error), "type": type(error).__name__})
            self._record_placeholder_cost(
                exec_ctx,
                step="mag",
                metadata={"stage": "mag", "status": "exception"},
            )
            exec_ctx.observer.finalize()

    def invoke_mag(
        self,
        slug: str,
        payload: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Invoke a Main Agent (MAG) with execution planning and cost tracking.

        Args:
            slug: Agent slug (e.g., "offer-orchestrator-mag")
            payload: Input data conforming to agent's input schema
            context: Optional context for distributed tracing and run_id retrieval.
                     If provided, the generated run_id will be written to context["run_id"].

        Returns:
            Output data conforming to agent's output schema

        Raises:
            Exception: If execution fails
        """
        context = context or {}
        run_id = f"mag-{uuid.uuid4().hex[:8]}"
        context["run_id"] = run_id
        exec_ctx: Optional[_ExecutionContext] = None

        try:
            exec_ctx = self._prepare_execution(slug, run_id, context)
            obs = exec_ctx.observer

            obs.log(
                "start",
                {
                    "agent": exec_ctx.agent.name,
                    "slug": slug,
                    "plan": self._plan_summary(exec_ctx.execution_plan, exec_ctx.llm_plan),
                    "llm_plan": obs.llm_plan_snapshot,
                },
            )

            # Execute MAG
            output, duration_ms = self._execute_mag(exec_ctx, payload)

            # Finalize and record success
            self._finalize_mag_success(exec_ctx, duration_ms)

            return output

        except Exception as e:
            self._handle_mag_error(exec_ctx, e)
            raise

    # ---------------------------------------------------------------------
    # Backward-compatible helper used by some tests: run a single agent
    # directly by slug, enforcing the async-only contract. This bypasses
    # planning/observability and is intended for unit tests.
    # ---------------------------------------------------------------------
    def run_agent(
        self,
        slug: str,
        payload: Dict[str, Any],
        *,
        observer: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Execute an agent entrypoint directly.

        This method exists for compatibility with unit tests that expect a
        simple runner surface. It enforces that the agent entrypoint is async
        and executes it safely from sync context.

        Args:
            slug: Agent slug to execute
            payload: Input payload passed to the agent
            observer: Optional observer passed through for tests

        Returns:
            Agent output dict
        """
        agent = self.registry.load_agent(slug)
        run_fn = self.registry.resolve_entrypoint(agent.entrypoint)

        if not _is_async_callable(run_fn):
            raise ValueError(
                f"Agent '{agent.slug}' must be async. Synchronous agents are not supported."
            )

        async def _run() -> Dict[str, Any]:
            return await run_fn(payload, skills=self.skills, obs=observer)  # type: ignore[no-any-return]

        return self._run_async_safely(_run())  # type: ignore[no-any-return]

    def _run_pre_evaluations(
        self,
        exec_ctx: _ExecutionContext,
        delegation: Delegation,
        context: Dict[str, Any],
    ) -> None:
        """
        Run pre-execution evaluations and enforce fail-closed policies.

        Args:
            exec_ctx: Execution context with observer
            delegation: Delegation request
            context: Execution context

        Raises:
            RuntimeError: If fail-closed pre-evaluation fails
        """
        obs = exec_ctx.observer
        pre_eval_results = self.evals.evaluate_all(
            delegation.sag_id, "pre_eval", delegation.input, context
        )
        if not pre_eval_results:
            return

        obs.log(
            "pre_eval",
            {
                "results": [
                    {
                        "eval_slug": r.eval_slug,
                        "passed": r.passed,
                        "score": r.overall_score,
                        "metrics": [
                            {"id": m.metric_id, "score": m.score, "passed": m.passed}
                            for m in r.metrics
                        ],
                    }
                    for r in pre_eval_results
                ]
            },
        )

        # Check if any critical pre-eval failed
        critical_failures = [r for r in pre_eval_results if not r.passed]
        if critical_failures:
            obs.log("pre_eval_failure", {"failed_evals": [r.eval_slug for r in critical_failures]})
            # Check fail_open/fail_closed behavior
            fail_closed_evals = [r for r in critical_failures if not r.fail_open]
            if fail_closed_evals:
                # Fail-closed: block execution
                failed_slugs = [r.eval_slug for r in fail_closed_evals]
                raise RuntimeError(
                    f"Pre-evaluation failed (fail-closed): {', '.join(failed_slugs)}"
                )

    def _run_post_evaluations(
        self,
        exec_ctx: _ExecutionContext,
        delegation: Delegation,
        output: Dict[str, Any],
        context: Dict[str, Any],
    ) -> None:
        """
        Run post-execution evaluations and enforce fail-closed policies.

        Args:
            exec_ctx: Execution context with observer
            delegation: Delegation request
            output: Agent output to evaluate
            context: Execution context

        Raises:
            RuntimeError: If fail-closed post-evaluation fails
        """
        obs = exec_ctx.observer
        post_eval_results = self.evals.evaluate_all(delegation.sag_id, "post_eval", output, context)
        if not post_eval_results:
            return

        obs.log(
            "post_eval",
            {
                "results": [
                    {
                        "eval_slug": r.eval_slug,
                        "passed": r.passed,
                        "score": r.overall_score,
                        "duration_ms": r.duration_ms,
                        "metrics": [
                            {
                                "id": m.metric_id,
                                "name": m.metric_name,
                                "score": m.score,
                                "passed": m.passed,
                                "threshold": m.threshold,
                                "details": m.details,
                            }
                            for m in r.metrics
                        ],
                    }
                    for r in post_eval_results
                ]
            },
        )

        # Check if any critical post-eval failed
        critical_failures = [r for r in post_eval_results if not r.passed]
        if critical_failures:
            obs.log("post_eval_failure", {"failed_evals": [r.eval_slug for r in critical_failures]})
            # Check fail_open/fail_closed behavior
            fail_closed_evals = [r for r in critical_failures if not r.fail_open]
            if fail_closed_evals:
                # Fail-closed: block execution and return error
                failed_slugs = [r.eval_slug for r in fail_closed_evals]
                raise RuntimeError(
                    f"Post-evaluation failed (fail-closed): {', '.join(failed_slugs)}"
                )

    async def _execute_agent_async(
        self,
        exec_ctx: _ExecutionContext,
        delegation: Delegation,
    ) -> tuple[Dict[str, Any], int]:
        """
        Execute the agent asynchronously and return output with duration.

        Args:
            exec_ctx: Execution context
            delegation: Delegation request

        Returns:
            Tuple of (output, duration_ms)
        """
        try:
            run_fn = self.registry.resolve_entrypoint(exec_ctx.agent.entrypoint)
            t0 = time.time()
            output: Dict[str, Any] = await run_fn(
                delegation.input, skills=self.skills, obs=exec_ctx.observer
            )
            duration_ms = int((time.time() - t0) * MS_PER_SECOND)
            return output, duration_ms
        finally:
            await self._cleanup_mcp_async()

    def _run_async_safely(self, coro: Coroutine[Any, Any, Any]) -> Any:
        """
        Run an async coroutine safely, handling both sync and async contexts.

        If already in an event loop (e.g., async MAG calling async SAG),
        runs the coroutine in a new thread with its own event loop to avoid
        RuntimeError from nested asyncio.run() calls.

        Args:
            coro: The coroutine to run

        Returns:
            The result of the coroutine

        Raises:
            Any exception raised by the coroutine
        """
        try:
            asyncio.get_running_loop()
            # We're already in an event loop - run in a new thread
            logger.debug("Detected running event loop, executing async agent in new thread")

            result_container = {}
            exception_container = {}

            def run_in_new_loop() -> None:
                try:
                    result_container["value"] = asyncio.run(coro)
                except Exception as e:
                    exception_container["error"] = e
                finally:
                    # Give MCP subprocess cleanup time to complete before thread exits
                    # This prevents "Event loop is closed" errors in BaseSubprocessTransport.__del__
                    time.sleep(0.5)

            thread = threading.Thread(target=run_in_new_loop)
            thread.start()
            thread.join()

            if "error" in exception_container:
                raise exception_container["error"]
            return result_container["value"]

        except RuntimeError:
            # No event loop running - safe to use asyncio.run() directly
            try:
                result = asyncio.run(coro)
                return result
            finally:
                # Give MCP subprocess cleanup time to complete
                time.sleep(0.5)

    def _execute_agent(
        self,
        exec_ctx: _ExecutionContext,
        delegation: Delegation,
    ) -> tuple[Dict[str, Any], int]:
        """
        Execute the agent and return output with duration.

        Automatically detects async agents and runs them appropriately.

        Args:
            exec_ctx: Execution context
            delegation: Delegation request

        Returns:
            Tuple of (output, duration_ms)
        """
        run_fn = self.registry.resolve_entrypoint(exec_ctx.agent.entrypoint)

        # Check if agent is async (handles async def, async __call__, and partials)
        if not _is_async_callable(run_fn):
            raise ValueError(
                f"Agent '{exec_ctx.agent.slug}' must be async. Synchronous agents are not supported."
            )

        logger.debug(f"Agent '{exec_ctx.agent.slug}' is async, using async execution")
        return self._run_async_safely(self._execute_agent_async(exec_ctx, delegation))  # type: ignore[no-any-return]

    def _build_success_metrics(
        self,
        exec_ctx: _ExecutionContext,
        duration_ms: int,
        attempt: int,
    ) -> Dict[str, Any]:
        """
        Build metrics dictionary for successful execution.

        Args:
            exec_ctx: Execution context with observer
            duration_ms: Execution duration
            attempt: Attempt number (0-indexed)

        Returns:
            Metrics dictionary
        """
        obs = exec_ctx.observer
        plan_snapshot = obs.llm_plan_snapshot
        metrics: Dict[str, Any] = {
            "duration_ms": duration_ms,
            "attempts": attempt + 1,
            "cost_usd": obs.cost_usd,
            "tokens": obs.token_count,
        }
        if plan_snapshot:
            metrics.update(
                {
                    "provider": plan_snapshot.get("provider"),
                    "model": plan_snapshot.get("model"),
                    "use_batch": plan_snapshot.get("use_batch"),
                    "use_cache": plan_snapshot.get("use_cache"),
                    "structured_output": plan_snapshot.get("structured_output"),
                    "moderation": plan_snapshot.get("moderation"),
                    "llm_plan": plan_snapshot,
                }
            )
        return metrics

    def _build_failure_result(
        self,
        exec_ctx: _ExecutionContext,
        delegation: Delegation,
        last_error: Optional[Exception],
        max_attempts: int,
    ) -> Result:
        """
        Build failure result after all retry attempts exhausted.

        Args:
            exec_ctx: Execution context
            delegation: Delegation request
            last_error: Last exception that occurred
            max_attempts: Maximum number of attempts made

        Returns:
            Result with failure status
        """
        obs = exec_ctx.observer
        self._record_placeholder_cost(
            exec_ctx,
            step=delegation.task_id,
            metadata={"stage": "sag", "attempts": max_attempts, "status": "failure"},
        )
        plan_snapshot = obs.llm_plan_snapshot
        failure_metrics: Dict[str, Any] = {
            "attempts": max_attempts,
            "cost_usd": obs.cost_usd,
            "tokens": obs.token_count,
        }
        if plan_snapshot:
            failure_metrics.update(
                {
                    "provider": plan_snapshot.get("provider"),
                    "model": plan_snapshot.get("model"),
                    "use_batch": plan_snapshot.get("use_batch"),
                    "use_cache": plan_snapshot.get("use_cache"),
                    "structured_output": plan_snapshot.get("structured_output"),
                    "moderation": plan_snapshot.get("moderation"),
                    "llm_plan": plan_snapshot,
                }
            )

        obs.log(
            "error",
            {
                "error": str(last_error),
                "attempts": max_attempts,
                "llm_plan": plan_snapshot,
            },
        )
        obs.finalize()

        return Result(
            task_id=delegation.task_id,
            status="failure",
            output={},
            metrics=failure_metrics,
            error=str(last_error),
        )

    async def invoke_sag_async(self, delegation: Delegation) -> Result:
        """
        Invoke a Sub-Agent (SAG) asynchronously with execution planning and cost tracking.

        This is the preferred method when calling from async context (e.g., async MAG).
        It avoids thread creation and nested event loops, allowing all execution to happen
        in the same event loop.

        Args:
            delegation: Delegation request with task_id, sag_id, input, context

        Returns:
            Result with status, output, metrics

        Raises:
            Exception: If execution fails (with retry logic applied)
        """
        run_id = f"sag-{uuid.uuid4().hex[:8]}"
        exec_ctx: Optional[_ExecutionContext] = None
        context = delegation.context or {}

        try:
            exec_ctx = self._prepare_execution(delegation.sag_id, run_id, context)
            obs = exec_ctx.observer

            obs.log(
                "start",
                {
                    "agent": exec_ctx.agent.name,
                    "slug": delegation.sag_id,
                    "task_id": delegation.task_id,
                    "parent_run_id": context.get("parent_run_id"),
                    "plan": self._plan_summary(exec_ctx.execution_plan, exec_ctx.llm_plan),
                    "llm_plan": obs.llm_plan_snapshot,
                },
            )

            # Retry policy
            retry_policy = exec_ctx.agent.evaluation.get("retry_policy", {})
            max_attempts = retry_policy.get("max_attempts", 1)
            backoff_ms = retry_policy.get("backoff_ms", 0)

            last_error = None
            for attempt in range(max_attempts):
                try:
                    # Run pre-evaluation checks
                    self._run_pre_evaluations(exec_ctx, delegation, context)

                    # Execute agent asynchronously in same event loop
                    output, duration_ms = await self._execute_agent_async(exec_ctx, delegation)

                    # Run post-evaluation checks
                    self._run_post_evaluations(exec_ctx, delegation, output, context)

                    # Record metrics and cost
                    obs.metric("duration_ms", duration_ms)
                    self._record_placeholder_cost(
                        exec_ctx,
                        step=delegation.task_id,
                        metadata={"stage": "sag", "attempt": attempt + 1},
                    )

                    # Build success metrics and log
                    metrics = self._build_success_metrics(exec_ctx, duration_ms, attempt)
                    obs.log(
                        "end",
                        {
                            "status": "success",
                            "attempt": attempt + 1,
                            "duration_ms": duration_ms,
                            "cost_usd": obs.cost_usd,
                            "tokens": obs.token_count,
                            "llm_plan": obs.llm_plan_snapshot,
                        },
                    )
                    obs.finalize()

                    return Result(
                        task_id=delegation.task_id,
                        status="success",
                        output=output,
                        metrics=metrics,
                    )

                except Exception as e:
                    last_error = e
                    obs.log(
                        "retry", {"attempt": attempt + 1, "error": str(e), "type": type(e).__name__}
                    )
                    if attempt < max_attempts - 1 and backoff_ms > 0:
                        await asyncio.sleep(backoff_ms / MS_PER_SECOND)

            # All attempts failed
            return self._build_failure_result(exec_ctx, delegation, last_error, max_attempts)

        except Exception as e:
            if exec_ctx is not None:
                self._record_placeholder_cost(
                    exec_ctx,
                    step=delegation.task_id,
                    metadata={"stage": "sag", "status": "exception"},
                )
                exec_ctx.observer.log("error", {"error": str(e), "type": type(e).__name__})
                exec_ctx.observer.finalize()
            raise

    def invoke_sag(self, delegation: Delegation) -> Result:
        """
        Invoke a Sub-Agent (SAG) with execution planning and cost tracking.

        This is a synchronous wrapper around invoke_sag_async() for backward compatibility.
        When called from async context (e.g., async MAG), prefer using invoke_sag_async() directly.

        Args:
            delegation: Delegation request with task_id, sag_id, input, context

        Returns:
            Result with status, output, metrics

        Raises:
            Exception: If execution fails (with retry logic applied)
        """
        run_id = f"sag-{uuid.uuid4().hex[:8]}"
        exec_ctx: Optional[_ExecutionContext] = None
        context = delegation.context or {}

        try:
            exec_ctx = self._prepare_execution(delegation.sag_id, run_id, context)
            obs = exec_ctx.observer

            obs.log(
                "start",
                {
                    "agent": exec_ctx.agent.name,
                    "slug": delegation.sag_id,
                    "task_id": delegation.task_id,
                    "parent_run_id": context.get("parent_run_id"),
                    "plan": self._plan_summary(exec_ctx.execution_plan, exec_ctx.llm_plan),
                    "llm_plan": obs.llm_plan_snapshot,
                },
            )

            # Retry policy
            retry_policy = exec_ctx.agent.evaluation.get("retry_policy", {})
            max_attempts = retry_policy.get("max_attempts", 1)
            backoff_ms = retry_policy.get("backoff_ms", 0)

            last_error = None
            for attempt in range(max_attempts):
                try:
                    # Run pre-evaluation checks
                    self._run_pre_evaluations(exec_ctx, delegation, context)

                    # Execute agent
                    output, duration_ms = self._execute_agent(exec_ctx, delegation)

                    # Run post-evaluation checks
                    self._run_post_evaluations(exec_ctx, delegation, output, context)

                    # Record metrics and cost
                    obs.metric("duration_ms", duration_ms)
                    self._record_placeholder_cost(
                        exec_ctx,
                        step=delegation.task_id,
                        metadata={"stage": "sag", "attempt": attempt + 1},
                    )

                    # Build success metrics and log
                    metrics = self._build_success_metrics(exec_ctx, duration_ms, attempt)
                    obs.log(
                        "end",
                        {
                            "status": "success",
                            "attempt": attempt + 1,
                            "duration_ms": duration_ms,
                            "cost_usd": obs.cost_usd,
                            "tokens": obs.token_count,
                            "llm_plan": obs.llm_plan_snapshot,
                        },
                    )
                    obs.finalize()

                    return Result(
                        task_id=delegation.task_id,
                        status="success",
                        output=output,
                        metrics=metrics,
                    )

                except Exception as e:
                    last_error = e
                    obs.log(
                        "retry", {"attempt": attempt + 1, "error": str(e), "type": type(e).__name__}
                    )
                    if attempt < max_attempts - 1 and backoff_ms > 0:
                        time.sleep(backoff_ms / MS_PER_SECOND)

            # All attempts failed
            return self._build_failure_result(exec_ctx, delegation, last_error, max_attempts)

        except Exception as e:
            if exec_ctx is not None:
                self._record_placeholder_cost(
                    exec_ctx,
                    step=delegation.task_id,
                    metadata={"stage": "sag", "status": "exception"},
                )
                exec_ctx.observer.log("error", {"error": str(e), "type": type(e).__name__})
                exec_ctx.observer.finalize()
            raise


# Singleton instance
_runner: Optional[AgentRunner] = None


def get_runner(base_dir: Optional[Path] = None) -> AgentRunner:
    """Get or create the global runner instance"""
    global _runner
    if _runner is None or base_dir is not None:
        _runner = AgentRunner(base_dir=base_dir)
    return _runner


def invoke_mag(
    slug: str,
    payload: Dict[str, Any],
    base_dir: Optional[Path] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Convenience function to invoke a MAG.

    Args:
        slug: Agent slug identifier
        payload: Input data conforming to agent's input schema
        base_dir: Optional base directory for run artifacts
        context: Optional context for distributed tracing and run_id retrieval.
                 If provided, the generated run_id will be written to context["run_id"].

    Returns:
        Output data conforming to agent's output schema
    """
    runner = get_runner(base_dir=base_dir)
    return runner.invoke_mag(slug, payload, context=context)


def invoke_sag(delegation: Delegation, base_dir: Optional[Path] = None) -> Result:
    """Convenience function to invoke a SAG"""
    runner = get_runner(base_dir=base_dir)
    return runner.invoke_sag(delegation)


__all__ = [
    "ObservabilityLogger",
    "Delegation",
    "Result",
    "SkillRuntime",
    "AgentRunner",
    "get_runner",
    "invoke_mag",
    "invoke_sag",
]
