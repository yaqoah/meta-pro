"""Bounded LangGraph state machine for Meta-Pro.

Supervisor pattern with an LLM-driven router:

    START -> supervisor ──strategy_agent──▶ strategy_agent ─┐
                        ──visual_agent────▶ visual_agent   ─┼──▶ supervisor
                        ──prompt_builder──▶ prompt_builder ─┘
                        ──FINISH──────────▶ END

Bounding:
- ``compute_state_hash`` digests the routing-relevant fields every step;
- ``check_bounds_and_cycles`` halts the run (via a ``FINISH`` route plus an
  ``error_log`` alert) when ``step_count >= MAX_STEPS`` or a state hash
  repeats — this is what terminates the ``INFINITE_LOOP`` chaos mode.

The supervisor decides the next worker through Instructor
(``SupervisorRoute``), degrades to deterministic routing when the LLM path
fails, and rejects malformed worker handoffs. Worker nodes call
``call_llm_with_resilience`` and degrade to deterministic placeholders on
schema/provider failures.

Checkpointing: ``PostgresSaver`` against ``DATABASE_URL`` when configured
(Supabase Supavisor pooler — see ``.env.example``; local Docker Postgres is
not used); otherwise a zero-dependency SQLite file via the optional
``langgraph-checkpoint-sqlite`` package; and finally an in-memory
``MemorySaver()``. The app therefore runs with **no external services** —
ideal for GitHub Codespaces / low-RAM machines without Docker. State-hash
cycle detection and step bounds travel inside ``MetaProState``
(``state_hashes`` / ``step_count`` channels) — backed by a plain Python dict
in the in-memory fallback — so they never depend on an external store.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    ChannelVersions,
)
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app import resilience
from app.config import settings
from app.schemas import (
    HookOption,
    MetaProState,
    PlatformStrategyOutput,
    PlatformType,
    SupervisorRoute,
)

logger = logging.getLogger(__name__)

PLATFORMS: tuple[PlatformType, ...] = (
    PlatformType.LINKEDIN,
    PlatformType.X_THREAD,
    PlatformType.MEDIUM,
)

WORKER_NODES = ("strategy_agent", "visual_agent", "prompt_builder")

# Every node key in the compiled graph — used to filter astream_events to
# node-level lifecycle events (conditional-edge runs are excluded).
NODE_NAMES = ("supervisor",) + WORKER_NODES


class _VisualDiagramOutput(BaseModel):
    """Structured output of the visual agent (local to the graph)."""

    visual_diagram_mermaid: str = Field(
        ..., description="Valid dark-mode Mermaid.js flowchart string"
    )


class _ClaudeMetaPromptOutput(BaseModel):
    """Structured output of the prompt builder (local to the graph)."""

    claude_meta_prompt: str = Field(
        ..., description="Context-stuffed prompt ready for Claude 3.5 Sonnet"
    )


# ---------------------------------------------------------------------------
# Bounding layer: state hashing, cycle detection, step bound
# ---------------------------------------------------------------------------


def compute_state_hash(state: MetaProState) -> str:
    """Stable SHA-256 digest over the fields that determine routing progress.

    Hashes the key fields (``transcript_text``, ``strategic_angle``,
    ``active_platform`` and the current ``strategy_results``), deliberately
    excluding ``step_count``, ``state_hashes`` and ``error_log``.

    Note: the full results *content* is hashed (not just the result keys) so
    that normal progress through strategy -> visual -> prompt on the same
    platform changes the digest; hashing only the keys would falsely trip
    cycle detection mid-pipeline.
    """
    payload = {
        "transcript_text": state.get("transcript_text", ""),
        "strategic_angle": state.get("strategic_angle"),
        "active_platform": state.get("active_platform"),
        "strategy_results": {
            key: result.model_dump(mode="json")
            for key, result in state.get("strategy_results", {}).items()
        },
    }
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _halt_reason(state: MetaProState) -> list[str]:
    """Pure: alert messages when the workflow must halt (bound or cycle)."""
    alerts: list[str] = []
    step_count = state.get("step_count", 0)
    if step_count >= settings.MAX_STEPS:
        alerts.append(
            f"Step bound hit: step_count {step_count} >= MAX_STEPS {settings.MAX_STEPS}"
        )
    digest = compute_state_hash(state)
    if digest in state.get("state_hashes", []):
        alerts.append(f"State-hash cycle detected: {digest[:12]}…")
    return alerts


def check_bounds_and_cycles(state: MetaProState) -> bool:
    """Return True when the run must terminate (step bound or state cycle).

    Appends an alert to ``state["error_log"]`` — the supervisor node
    re-returns ``error_log`` in its update so the alert persists in state.
    """
    alerts = _halt_reason(state)
    if alerts:
        state["error_log"] = state.get("error_log", []) + alerts
        return True
    return False


def _halted(state: MetaProState) -> bool:
    """Pure halt check used by conditional edges (never mutates state)."""
    return bool(_halt_reason(state))


def _bump(state: MetaProState) -> tuple[int, list[str]]:
    """Increment the step counter and record the received state's digest."""
    step_count = state.get("step_count", 0) + 1
    digest = compute_state_hash(state)
    return step_count, state.get("state_hashes", []) + [digest]


# ---------------------------------------------------------------------------
# Supervisor & worker nodes
# ---------------------------------------------------------------------------


def _platform_for(state: MetaProState, worker: str) -> PlatformType | None:
    """First platform still pending work for ``worker``, if any."""
    results = state.get("strategy_results", {})
    if worker == "strategy_agent":
        return next((p for p in PLATFORMS if p.value not in results), None)
    if worker == "visual_agent":
        return next(
            (
                p
                for p in PLATFORMS
                if results.get(p.value) and not results[p.value].visual_diagram_mermaid
            ),
            None,
        )
    if worker == "prompt_builder":
        return next(
            (
                p
                for p in PLATFORMS
                if results.get(p.value) and not results[p.value].claude_meta_prompt
            ),
            None,
        )
    return None


def _deterministic_route(state: MetaProState) -> SupervisorRoute:
    """Phase-based routing used when the LLM route is unavailable."""
    for worker, reason in (
        ("strategy_agent", "needs a platform strategy"),
        ("visual_agent", "needs a dark-mode Mermaid diagram"),
        ("prompt_builder", "needs a Claude 3.5 meta-prompt"),
    ):
        platform = _platform_for(state, worker)
        if platform is not None:
            return SupervisorRoute(
                next_worker=worker,  # type: ignore[arg-type]
                reasoning=f"{platform.value} {reason}",
            )
    return SupervisorRoute(
        next_worker="FINISH",  # type: ignore[arg-type]
        reasoning="All platforms complete",
    )


def _validate_handoffs(state: MetaProState) -> str | None:
    """Return an alert string when a stored worker handoff breaks the contract."""
    results = state.get("strategy_results", {})
    for platform in PLATFORMS:
        result = results.get(platform.value)
        if result is None:
            continue
        if result.platform != platform:
            return (
                f"supervisor: malformed handoff — {platform.value} result "
                f"declares platform {result.platform.value}"
            )
        if len(result.hooks) != 3:
            return (
                f"supervisor: malformed handoff — {platform.value} has "
                f"{len(result.hooks)} hooks (contract requires 3)"
            )
    return None


def supervisor_node(state: MetaProState) -> dict:
    """Single decision point: halt, loop-chaos, or LLM route (with recovery)."""
    # 1) Bounds and cycles always win.
    if check_bounds_and_cycles(state):
        return {
            "supervisor_route": SupervisorRoute(
                next_worker="FINISH",
                reasoning="Halted by step bound or state-hash cycle",
            ),
            "error_log": state["error_log"],
        }

    # 2) INFINITE_LOOP chaos: ping-pong between workers so cycle detection fires.
    if state.get("chaos_injection_flag") == "INFINITE_LOOP":
        platform = state.get("active_platform") or PlatformType.LINKEDIN
        if state.get("step_count", 0) % 2 == 0:
            route = SupervisorRoute(
                next_worker="strategy_agent",  # type: ignore[arg-type]
                reasoning="INFINITE_LOOP chaos: strategy leg of the ping-pong",
            )
        else:
            route = SupervisorRoute(
                next_worker="visual_agent",  # type: ignore[arg-type]
                reasoning="INFINITE_LOOP chaos: visual leg of the ping-pong",
            )
        return {"supervisor_route": route, "active_platform": platform}

    # 3) Reject malformed worker handoffs.
    alert = _validate_handoffs(state)
    if alert:
        return {
            "supervisor_route": SupervisorRoute(
                next_worker="FINISH",
                reasoning=alert,
            ),
            "error_log": state.get("error_log", []) + [alert],
        }

    # 4) LLM routing via Instructor, with deterministic recovery.
    try:
        route = resilience.call_llm_with_resilience(
            _supervisor_prompt(state),
            SupervisorRoute,
            chaos_flag=state.get("chaos_injection_flag"),
        )
    except (resilience.SchemaValidationError, resilience.SimulatedAPIError) as exc:
        error_log = state.get("error_log", []) + [
            f"supervisor: LLM route degraded ({exc}); using deterministic routing"
        ]
        route = _deterministic_route(state)
        if route.next_worker == "FINISH":
            return {"supervisor_route": route, "error_log": error_log}
        return {
            "supervisor_route": route,
            "active_platform": _platform_for(state, route.next_worker),
            "error_log": error_log,
        }

    if route.next_worker == "FINISH":
        return {"supervisor_route": route}

    platform = _platform_for(state, route.next_worker)
    if platform is None:
        # LLM suggested a worker with nothing left to do — correct it.
        route = _deterministic_route(state)
        if route.next_worker == "FINISH":
            return {"supervisor_route": route}
        platform = _platform_for(state, route.next_worker)
    return {"supervisor_route": route, "active_platform": platform}


def _angle_str(state: MetaProState) -> str:
    angle = state.get("strategic_angle")
    return angle.value if angle else "technical"


def _pipeline_status(state: MetaProState) -> str:
    lines: list[str] = []
    for platform in PLATFORMS:
        result = state.get("strategy_results", {}).get(platform.value)
        if result is None:
            lines.append(f"- {platform.value}: pending")
        else:
            lines.append(
                f"- {platform.value}: strategy=done "
                f"visual={'done' if result.visual_diagram_mermaid else 'pending'} "
                f"prompt={'done' if result.claude_meta_prompt else 'pending'}"
            )
    return "\n".join(lines)


def _supervisor_prompt(state: MetaProState) -> str:
    return (
        "You are the routing supervisor of a multi-agent content pipeline.\n"
        f"Transcript: {state.get('transcript_text', '')[:1200]}\n"
        f"Focus direction: {state.get('focus_direction', '')}\n"
        f"Strategic angle: {_angle_str(state)}\n"
        "Pipeline status:\n"
        f"{_pipeline_status(state)}\n"
        "Pick the next worker: 'strategy_agent' if a platform has no strategy, "
        "'visual_agent' if a strategy lacks a Mermaid diagram, 'prompt_builder' "
        "if a diagram lacks a Claude meta-prompt, else 'FINISH'.\n"
        "Return ONLY a SupervisorRoute with next_worker and one-line reasoning."
    )


def _strategy_prompt(state: MetaProState, platform: PlatformType) -> str:
    return (
        "You are the strategy agent of a content pipeline.\n"
        f"Target platform: {platform.value}\n"
        f"Strategic angle: {_angle_str(state)}\n"
        f"Focus direction: {state.get('focus_direction', '')}\n"
        f"Transcript: {state.get('transcript_text', '')[:3000]}\n"
        "Produce a PlatformStrategyOutput with exactly 3 HookOption entries "
        "(ids h1/h2/h3, each with style, headline and reasoning), an "
        "algorithm_checklist of platform mechanics, and leave "
        "visual_diagram_mermaid and claude_meta_prompt empty.\n"
        f"The platform field MUST be {platform.value}."
    )


def _visual_prompt(state: MetaProState, result: PlatformStrategyOutput) -> str:
    return (
        "You are the visual agent of a content pipeline.\n"
        f"Platform: {result.platform.value}\n"
        f"Headlines: {', '.join(h.headline for h in result.hooks)}\n"
        f"Transcript: {state.get('transcript_text', '')[:3000]}\n"
        "Extract the architecture / system-design concepts and emit a valid "
        "dark-mode Mermaid.js flowchart (fill:#1e1e2e background, light text).\n"
        "Return ONLY the mermaid code in the visual_diagram_mermaid field."
    )


def _prompt_prompt(state: MetaProState, result: PlatformStrategyOutput) -> str:
    return (
        "You are the prompt builder of a content pipeline.\n"
        f"Platform: {result.platform.value}\n"
        f"Strategic angle: {_angle_str(state)}\n"
        f"Focus direction: {state.get('focus_direction', '')}\n"
        f"Hooks: {', '.join(h.headline for h in result.hooks)}\n"
        f"Algorithm checklist: {', '.join(result.algorithm_checklist)}\n"
        f"Mermaid diagram:\n{result.visual_diagram_mermaid}\n"
        "Compile a context-stuffed, ready-to-use meta-prompt engineered for "
        "Claude 3.5 Sonnet that rewrites the transcript into a platform-native "
        "post. Return ONLY the prompt in the claude_meta_prompt field."
    )


def strategy_agent_node(state: MetaProState) -> dict:
    """Synthesize 3 hooks + platform mechanics via structured LLM output."""
    step_count, state_hashes = _bump(state)
    platform = state.get("active_platform") or PlatformType.LINKEDIN
    error_log = list(state.get("error_log", []))
    try:
        result = resilience.call_llm_with_resilience(
            _strategy_prompt(state, platform),
            PlatformStrategyOutput,
            chaos_flag=state.get("chaos_injection_flag"),
        )
    except (resilience.SchemaValidationError, resilience.SimulatedAPIError) as exc:
        error_log.append(
            f"strategy_agent: LLM degraded ({exc}); using placeholder strategy"
        )
        result = _placeholder_strategy(platform)
    else:
        if result.platform != platform:  # reject malformed handoff
            error_log.append(
                f"strategy_agent: rejected malformed handoff — LLM returned "
                f"{result.platform.value}, expected {platform.value}"
            )
            result = _placeholder_strategy(platform)
    results = dict(state.get("strategy_results", {}))
    results[platform.value] = result
    return {
        "step_count": step_count,
        "state_hashes": state_hashes,
        "strategy_results": results,
        "error_log": error_log,
    }


def visual_agent_node(state: MetaProState) -> dict:
    """Extract architecture concepts and emit a dark-mode Mermaid flowchart."""
    step_count, state_hashes = _bump(state)
    platform = state.get("active_platform")
    results = dict(state.get("strategy_results", {}))
    error_log = list(state.get("error_log", []))
    if platform is None or platform.value not in results:
        error_log.append(f"visual_agent: no strategy handoff for {platform} — rejected")
        return {
            "step_count": step_count,
            "state_hashes": state_hashes,
            "error_log": error_log,
        }
    result = results[platform.value]
    try:
        output = resilience.call_llm_with_resilience(
            _visual_prompt(state, result),
            _VisualDiagramOutput,
            chaos_flag=state.get("chaos_injection_flag"),
        )
        diagram = output.visual_diagram_mermaid
    except (resilience.SchemaValidationError, resilience.SimulatedAPIError) as exc:
        error_log.append(
            f"visual_agent: LLM degraded ({exc}); using placeholder diagram"
        )
        diagram = _placeholder_mermaid(result)
    results[platform.value] = result.model_copy(
        update={"visual_diagram_mermaid": diagram}
    )
    return {
        "step_count": step_count,
        "state_hashes": state_hashes,
        "strategy_results": results,
        "error_log": error_log,
    }


def prompt_builder_node(state: MetaProState) -> dict:
    """Compile a context-stuffed Claude 3.5 Sonnet meta-prompt."""
    step_count, state_hashes = _bump(state)
    platform = state.get("active_platform")
    results = dict(state.get("strategy_results", {}))
    error_log = list(state.get("error_log", []))
    if platform is None or platform.value not in results:
        error_log.append(
            f"prompt_builder: no strategy handoff for {platform} — rejected"
        )
        return {
            "step_count": step_count,
            "state_hashes": state_hashes,
            "error_log": error_log,
        }
    result = results[platform.value]
    try:
        output = resilience.call_llm_with_resilience(
            _prompt_prompt(state, result),
            _ClaudeMetaPromptOutput,
            chaos_flag=state.get("chaos_injection_flag"),
        )
        meta_prompt = output.claude_meta_prompt
    except (resilience.SchemaValidationError, resilience.SimulatedAPIError) as exc:
        error_log.append(
            f"prompt_builder: LLM degraded ({exc}); using placeholder meta-prompt"
        )
        meta_prompt = _placeholder_meta_prompt(result)
    results[platform.value] = result.model_copy(
        update={"claude_meta_prompt": meta_prompt}
    )
    return {
        "step_count": step_count,
        "state_hashes": state_hashes,
        "strategy_results": results,
        "error_log": error_log,
    }


# ---------------------------------------------------------------------------
# Deterministic placeholders used when the LLM path degrades
# ---------------------------------------------------------------------------


def _placeholder_strategy(platform: PlatformType) -> PlatformStrategyOutput:
    """Stand-in strategy — used only when the LLM path is unavailable."""
    return PlatformStrategyOutput(
        platform=platform,
        hooks=[
            HookOption(
                id="h1",
                style="contrarian",
                headline=f"{platform.value}: flip the default assumption",
                reasoning="Contrarian hooks earn curiosity-driven engagement.",
            ),
            HookOption(
                id="h2",
                style="stat-led",
                headline=f"{platform.value}: the number that changes the frame",
                reasoning="Specific numbers boost credibility and CTR.",
            ),
            HookOption(
                id="h3",
                style="story",
                headline=f"{platform.value}: open in the middle of the story",
                reasoning="Story-openers reduce bounce on long-form feeds.",
            ),
        ],
        algorithm_checklist=[
            "First 3 words carry the promise",
            "Line breaks every ~2 sentences",
            "End with a clear CTA / question",
            "Native hashtag & link conventions",
        ],
        visual_diagram_mermaid="",  # filled by visual_agent
        claude_meta_prompt="",  # filled by prompt_builder
    )


def _placeholder_mermaid(result: PlatformStrategyOutput) -> str:
    """Dark-mode Mermaid flowchart stand-in."""
    headline = result.hooks[0].headline.replace('"', "'")
    return (
        "flowchart TD\n"
        f'    A["{headline}"] --> B["Hook 1"]\n'
        '    A --> C["Hook 2"]\n'
        '    A --> D["Hook 3"]\n'
        "    style A fill:#1e1e2e,stroke:#89b4fa,color:#cdd6f4\n"
        "    style B fill:#313244,stroke:#a6e3a1,color:#cdd6f4\n"
        "    style C fill:#313244,stroke:#f9e2af,color:#cdd6f4\n"
        "    style D fill:#313244,stroke:#f38ba8,color:#cdd6f4\n"
    )


def _placeholder_meta_prompt(result: PlatformStrategyOutput) -> str:
    """Stuffed Claude 3.5 Sonnet prompt stand-in."""
    checklist = "\n".join(f"- {item}" for item in result.algorithm_checklist)
    return (
        "You are Claude 3.5 Sonnet, an elite social-content editor.\n"
        f"Platform: {result.platform.value}\n"
        f"Headline: {result.hooks[0].headline}\n"
        f"Algorithm checklist:\n{checklist}\n"
        "Task: rewrite the source transcript into a platform-native post that "
        "maximizes reach. Output only the post body.\n"
    )


# ---------------------------------------------------------------------------
# Graph assembly & checkpointer
# ---------------------------------------------------------------------------


def _route_next(state: MetaProState) -> str:
    """Conditional-edge selector: next node, or END when bound/cycle trips."""
    if _halted(state):
        return END
    route = state.get("supervisor_route")
    if route is None or route.next_worker == "FINISH":
        return END
    return route.next_worker


def _with_connect_timeout(url: str, seconds: int) -> str:
    """Append ``connect_timeout`` to a Postgres conninfo string."""
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}connect_timeout={seconds}"


def _with_required_ssl(url: str) -> str:
    """Ensure ``sslmode=require`` on Supabase (Supavisor) connection strings.

    Supabase's pooler requires TLS. If the URL already declares an
    ``sslmode`` parameter (e.g. ``sslmode=require`` in ``.env.example``) it
    is left untouched; otherwise ``sslmode=require`` is appended. Non-Supabase
    hosts are also left untouched so the string stays usable against any
    plain local Postgres.
    """
    if "supabase.com" not in url or "sslmode=" in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}sslmode=require"


def _redact_dsn(url: str) -> str:
    """Mask the password in a Postgres conninfo string for log output."""
    if "://" not in url or "@" not in url:
        return url
    scheme, _, rest = url.partition("://")
    credentials, _, host = rest.rpartition("@")
    if ":" not in credentials:
        return url
    user, _, _password = credentials.rpartition(":")
    return f"{scheme}://{user}:***@{host}"


def build_checkpointer() -> BaseCheckpointSaver:
    """Return the best available checkpointer without requiring external services.

    Priority:

    1. ``PostgresSaver`` over ``settings.DATABASE_URL`` — only when set
       (Supabase via its Supavisor connection pooler); falls through on any
       failure (e.g. invalid credentials, unreachable pooler, or an empty/
       malformed URL during quick local testing).
    2. ``SqliteSaver`` over ``settings.CHECKPOINT_SQLITE_URL`` — a plain
       SQLite file via the optional ``langgraph-checkpoint-sqlite`` package.
    3. ``MemorySaver`` — an in-process dict, guaranteed to work everywhere.

    Cycle detection and step bounds never need a database: they live in the
    ``state_hashes`` / ``step_count`` ``MetaProState`` channels, which the
    checkpointer persists — and ``MemorySaver`` itself is a plain Python dict.
    """
    # 1) Postgres — only when explicitly configured (Supabase).
    if settings.DATABASE_URL:
        conn = None
        try:
            import psycopg
            from langgraph.checkpoint.postgres import PostgresSaver
            from psycopg.rows import dict_row

            class _AsyncCompatiblePostgresSaver(PostgresSaver):
                """Sync ``PostgresSaver`` that also satisfies the async API.

                The SSE endpoint streams via ``astream_events``, which drives
                ``AsyncPregelLoop`` — that loop requires async checkpoint
                methods (``aget_tuple``, ``aput``, ``aput_writes``,
                ``alist``). The plain sync ``PostgresSaver`` does not
                implement them, so the base class raises
                ``NotImplementedError`` on the very first checkpoint read
                (the ``workflow streaming failed`` traceback seen with
                Supabase). This subclass delegates each async method to its
                sync implementation through ``asyncio.to_thread``. A lock
                serializes access to the single shared psycopg connection,
                which is not thread-safe under concurrent requests. All sync
                entry points (``/run``, ``/api/history``) are untouched.
                """

                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self._db_lock = asyncio.Lock()

                async def aget_tuple(
                    self, config: RunnableConfig
                ) -> CheckpointTuple | None:
                    async with self._db_lock:
                        return await asyncio.to_thread(self.get_tuple, config)

                async def aput(
                    self,
                    config: RunnableConfig,
                    checkpoint: Checkpoint,
                    metadata: CheckpointMetadata,
                    new_versions: ChannelVersions,
                ) -> RunnableConfig:
                    async with self._db_lock:
                        return await asyncio.to_thread(
                            self.put, config, checkpoint, metadata, new_versions
                        )

                async def aput_writes(
                    self,
                    config: RunnableConfig,
                    writes: Sequence[tuple[str, Any]],
                    task_id: str,
                    task_path: str = "",
                ) -> None:
                    async with self._db_lock:
                        await asyncio.to_thread(
                            self.put_writes, config, writes, task_id, task_path
                        )

                async def alist(
                    self,
                    config: RunnableConfig | None,
                    *,
                    filter: dict[str, Any] | None = None,
                    before: RunnableConfig | None = None,
                    limit: int | None = None,
                ) -> AsyncIterator[CheckpointTuple]:
                    # Collect under the lock, then yield after releasing it
                    # so consumers can interleave other checkpoint calls.
                    async with self._db_lock:

                        def _collect() -> list[CheckpointTuple]:
                            return list(
                                self.list(
                                    config,
                                    filter=filter,
                                    before=before,
                                    limit=limit,
                                )
                            )

                        items = await asyncio.to_thread(_collect)
                    for item in items:
                        yield item

            conn = psycopg.connect(
                _with_required_ssl(
                    _with_connect_timeout(settings.DATABASE_URL, 2)
                ),
                autocommit=True,
                # Supavisor (Supabase's pooler) transaction mode does not
                # support server-side prepared statements. Disabling them
                # (None, not 0) prevents "prepared statement already exists"
                # collisions when connections are routed across pooler
                # backends on port 6543.
                prepare_threshold=None,
                # PostgresSaver reads rows by column name (required).
                row_factory=dict_row,
            )
            # Async-compatible wrapper: the SSE endpoint streams via
            # ``astream_events`` (AsyncPregelLoop), which requires the async
            # checkpoint methods this subclass provides.
            checkpointer = _AsyncCompatiblePostgresSaver(conn)
            checkpointer.setup()
            logger.info(
                "Checkpointer: PostgresSaver (%s)",
                _redact_dsn(settings.DATABASE_URL),
            )
            return checkpointer
        except Exception as exc:
            logger.warning(
                "Postgres checkpointer unavailable (%s); trying SQLite", exc
            )
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    # 2) SQLite file — zero external services.
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver

        checkpointer = SqliteSaver.from_conn_string(settings.CHECKPOINT_SQLITE_URL)
        checkpointer.setup()
        logger.info(
            "Checkpointer: SqliteSaver (%s)", settings.CHECKPOINT_SQLITE_URL
        )
        return checkpointer
    except Exception as exc:
        # Default path (no DATABASE_URL) — info; opted-in path — warning.
        if settings.DATABASE_URL:
            logger.warning(
                "SQLite checkpointer unavailable (%s); using MemorySaver", exc
            )
        else:
            logger.info(
                "SQLite checkpointer unavailable (%s); using MemorySaver", exc
            )

    # 3) In-memory fallback.
    logger.info("Checkpointer: MemorySaver (no external database)")
    return MemorySaver()


def build_workflow(checkpointer: BaseCheckpointSaver | None = None):
    """Assemble and compile the bounded Meta-Pro state machine."""
    builder = StateGraph(MetaProState)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("strategy_agent", strategy_agent_node)
    builder.add_node("visual_agent", visual_agent_node)
    builder.add_node("prompt_builder", prompt_builder_node)

    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges("supervisor", _route_next)
    for worker in WORKER_NODES:
        builder.add_edge(worker, "supervisor")

    return builder.compile(checkpointer=checkpointer or build_checkpointer())


# Compiled workflow with persistent checkpointing (MemorySaver when Postgres
# is unavailable during local development).
workflow = build_workflow()
