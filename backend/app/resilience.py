"""Resilience layer for Meta-Pro.

Provides:
- Multi-provider LLM routing via LiteLLM (Mistral primary, Groq fallback)
  with structured output via Instructor (``instructor.from_litellm``).
- Tenacity retry with Retry-After-aware exponential backoff, a global
  request-pacing throttle (``MIN_LLM_INTERVAL_SECONDS``) and a logging
  hook on retries.
- ``call_llm_with_resilience`` entrypoint with chaos-engineering hooks.
- Step-budget guard (``MAX_STEPS``) and cycle detection via state digests.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from typing import Any, Callable, Dict, TypeVar

from pydantic import BaseModel
from tenacity import (
    Retrying,
    before_sleep_log,
    stop_after_attempt,
)

from app.config import settings
from app.schemas import ChaosInjectionFlag

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Logical model name resolved by LiteLLM to the [Mistral → Groq] failover group.
LLM_ALIAS = "meta-pro-llm"

# Shared LiteLLM Router resolving ``LLM_ALIAS`` to its deployment(s). The
# alias mechanism only works through a Router — plain ``litellm.completion``
# rejects unknown model names with ``BadRequestError: LLM Provider NOT
# provided`` (the crash seen with Supabase + the SSE stream).
_ROUTER: Any | None = None

# instructor + litellm are imported lazily so the app can boot — and degrade
# to deterministic routing / placeholder strategies — in minimal environments
# where the provider SDKs are not installed (e.g. Dockerless local runs).
_llm_stack: bool | None = None


def _llm_stack_available() -> bool:
    """Return (cached) whether instructor + litellm are importable."""
    global _llm_stack
    if _llm_stack is None:
        try:
            import instructor  # noqa: F401
            import litellm  # noqa: F401
            _llm_stack = True
        except ImportError:
            _llm_stack = False
    return _llm_stack


class MaxStepsExceeded(Exception):
    """Raised when the graph exceeds the MAX_STEPS budget."""


class CycleDetected(Exception):
    """Raised when the graph revisits an identical state (infinite-loop guard)."""


class SimulatedAPIError(RuntimeError):
    """Models a 500 Internal Server Error from the upstream provider."""


class LLMUnavailableError(SimulatedAPIError):
    """Raised when the LLM provider stack (instructor/litellm) is unavailable.

    Subclasses :class:`SimulatedAPIError` so the graph's existing degradation
    handlers (which catch ``SimulatedAPIError``) fall through to deterministic
    placeholders without modification.
    """


class ProviderUnavailableError(SimulatedAPIError):
    """Raised when the upstream LLM provider errors out after retries.

    Covers rate limits (HTTP 429), 5xx failures, timeouts and invalid
    responses surfaced by LiteLLM / Instructor. Subclasses
    :class:`SimulatedAPIError` so the graph's degradation handlers degrade
    that node to deterministic placeholders instead of crashing the whole
    run — a rate-limited or down provider must not kill the pipeline.
    """


class SchemaValidationError(Exception):
    """Models a corrupt/invalid payload rejected at worker handoff."""


def state_digest(state: Dict[str, Any]) -> str:
    """Stable SHA-256 digest of a state dict, for cycle detection."""

    def _serialize(value: Any) -> Any:
        if isinstance(value, BaseModel):
            return value.model_dump(mode="json")
        return str(value)

    canonical = json.dumps(state, sort_keys=True, default=_serialize)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def assert_step_budget(step_count: int, max_steps: int | None = None) -> None:
    """Raise :class:`MaxStepsExceeded` once the worker step budget is used up."""
    budget = settings.MAX_STEPS if max_steps is None else max_steps
    if step_count > budget:
        raise MaxStepsExceeded(
            f"Step budget exceeded: {step_count} > {budget} (MAX_STEPS)"
        )


def assert_no_cycle(state_hashes: list[str], digest: str) -> None:
    """Raise :class:`CycleDetected` if this exact state was already visited."""
    if digest in state_hashes:
        raise CycleDetected(
            f"State repeated — possible infinite loop ({digest[:12]}…)"
        )


# --------------------------------------------------------------------------
# LLM routing & retry layer
# --------------------------------------------------------------------------

def _extract_retry_after(exc: Exception) -> float | None:
    """Return the provider's ``Retry-After`` hint in seconds, if any.

    Walks the exception and its ``__cause__`` (LiteLLM wraps the underlying
    provider error, e.g. ``MistralException``) looking for an HTTP response
    carrying a ``Retry-After`` header, plus any ``retry_after`` attribute
    LiteLLM copied onto the exception directly. Returns ``None`` when the
    provider did not signal a wait (non-429 failures, missing headers).
    """
    for candidate in (exc, getattr(exc, "__cause__", None)):
        if candidate is None:
            continue
        retry_after = getattr(candidate, "retry_after", None)
        if isinstance(retry_after, (int, float)):
            return float(retry_after)
        response = getattr(candidate, "response", None)
        headers = getattr(response, "headers", None)
        if headers is None:
            continue
        # httpx ``Headers`` is case-insensitive; plain dicts are not, so
        # probe both spellings.
        value = headers.get("retry-after") or headers.get("Retry-After")
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _is_rate_limit(exc: Exception) -> bool:
    """True when the failure chain is an HTTP 429 (provider rate limit)."""
    for candidate in (exc, getattr(exc, "__cause__", None)):
        if candidate is None:
            continue
        if getattr(candidate, "status_code", None) == 429:
            return True
        if getattr(candidate, "raw_status_code", None) == 429:
            return True
    return False


# Upper bound on the total time one call may spend sleeping between
# retries (``MAX_RETRY_AFTER_SECONDS`` + margin). Keeps a rate-limited run
# from stalling for minutes: the first wait can honour a long Retry-After,
# but the whole retry sequence still degrades within about a minute.
_TOTAL_RETRY_BUDGET = settings.MAX_RETRY_AFTER_SECONDS + 15.0


def _retry_wait(retry_state: Any) -> float:
    """Tenacity wait: honour the provider's ``Retry-After``, else exponential.

    The old fixed backoff (2s/4s/10s) slept *inside* Mistral's rate-limit
    window, so every retry of a 429 failed again. When the provider says how
    long to wait, wait that long (capped by ``MAX_RETRY_AFTER_SECONDS``);
    otherwise fall back to the previous exponential schedule (2s, 4s, 8s, …
    clamped to 10s). Every wait is clipped to the remaining
    ``_TOTAL_RETRY_BUDGET`` so a fully rate-limited node degrades (breaker
    trips, placeholders) within about a minute instead of re-waiting 60s
    per attempt.
    """
    attempt = max(0, retry_state.attempt_number - 1)
    backoff = min(2.0 * (2 ** attempt), 10.0)
    budget_left = max(
        0.0, _TOTAL_RETRY_BUDGET - retry_state.seconds_since_start
    )
    outcome = retry_state.outcome
    if outcome is not None and outcome.exception() is not None:
        retry_after = _extract_retry_after(outcome.exception())
        if retry_after is not None:
            return min(
                max(backoff, min(retry_after, settings.MAX_RETRY_AFTER_SECONDS)),
                budget_left,
            )
    return min(backoff, budget_left)


# Tenacity policy: Retry-After-aware exponential backoff (see ``_retry_wait``),
# at most 3 attempts, with a WARNING log hook before every retry sleep.
# A Retrying instance (not the @retry decorator factory) so the policy is
# directly inspectable — e.g. ``LLM_RETRY.stop.max_attempt_number``.
LLM_RETRY = Retrying(
    wait=_retry_wait,
    stop=stop_after_attempt(3),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)

# Consecutive-failure circuit breaker. Once the provider has failed
# ``_BREAKER_LIMIT`` calls in a row, further LLM calls fast-fail for
# ``settings.BREAKER_COOLDOWN_SECONDS`` instead of burning backoff retries
# — so a rate-limited (429) or down provider degrades the rest of the run
# to placeholders quickly rather than stalling every node on backoff
# sleeps. The breaker re-arms the provider after the cooldown so a
# recovered key is retried; any success resets the failure count.
#
# ``_BREAKER_LIMIT`` intentionally matches ``LLM_RETRY``'s
# ``stop_after_attempt(3)`` so the trip lands on the final retry. The state
# is process-global and not locked: for this single-user server the worst
# case is one extra provider call (a non-atomic ``+=`` race under concurrent
# requests) or a degraded request while another request is on cooldown.
_BREAKER_LIMIT = 3
_breaker_failures = 0
_breaker_tripped_at: float | None = None

# --- Request pacing --------------------------------------------------------
# Global throttle so a single-user server can never exceed a provider's
# requests-per-minute quota (Mistral's free tier is ~60 RPM with tight
# per-minute token ceilings — the 429s seen in the logs). Every provider
# call waits until ``MIN_LLM_INTERVAL_SECONDS`` (+ any boost) has elapsed
# since the previous one. After a 429 the interval is widened for a few
# minutes so the provider has room to recover. Like the breaker, the state
# is process-global; the lock only guards the pacing bookkeeping itself.
_pacing_lock = threading.Lock()
_last_call_at = 0.0
_pacing_boost = 0.0  # extra seconds added after a 429
_pacing_boost_at: float | None = None
_PACING_BOOST_CAP = 120.0
_PACING_BOOST_WINDOW = 300.0  # boost decays 5 minutes after the last 429


def _effective_pacing_interval() -> float:
    """Current min interval between provider calls (base + decayed boost)."""
    global _pacing_boost, _pacing_boost_at
    with _pacing_lock:
        if _pacing_boost_at is not None and (
            time.monotonic() - _pacing_boost_at > _PACING_BOOST_WINDOW
        ):
            _pacing_boost = 0.0
            _pacing_boost_at = None
        return settings.MIN_LLM_INTERVAL_SECONDS + _pacing_boost


def _pace_call() -> None:
    """Block until the pacing window allows the next provider call.

    Reserves the next slot under the lock (so concurrent callers queue up
    ``interval`` seconds apart), then sleeps *outside* the lock — a
    ``/api/health`` probe or another call must never block on the sleep
    itself.
    """
    interval = _effective_pacing_interval()
    if interval <= 0:
        return
    with _pacing_lock:
        global _last_call_at
        now = time.monotonic()
        next_slot = max(now, _last_call_at + interval)
        _last_call_at = next_slot  # reserve this call's slot
        wait = next_slot - now
    if wait > 0:
        time.sleep(wait)


def _note_rate_limited(retry_after: float | None) -> None:
    """Widen the pacing interval after a 429 so the provider can recover.

    Every 429 refreshes the boost window (a sustained rate limit keeps the
    wider interval active) and raises the boost when the provider suggests
    a longer wait than the current one.
    """
    global _pacing_boost, _pacing_boost_at
    base = settings.MIN_LLM_INTERVAL_SECONDS
    suggested = max(base * 2, retry_after or 0.0)
    with _pacing_lock:
        _pacing_boost = min(max(_pacing_boost, suggested), _PACING_BOOST_CAP)
        _pacing_boost_at = time.monotonic()


def _configure_litellm_router() -> None:
    """Route ``LLM_ALIAS`` to the primary model with optional failover.

    Builds a :class:`litellm.Router` whose ``model_list`` maps ``LLM_ALIAS``
    to the primary model (Mistral). When ``GROQ_API_KEY`` is set, a Groq
    deployment is registered under its own model name and wired in via
    ``fallbacks``, so LiteLLM only uses it after the primary fails on a
    provider error / timeout — preserving a strict *primary-then-fallback*
    ordering (a shared alias across deployments would instead shuffle
    requests between providers). When Groq is not configured, the router
    holds only Mistral — Groq is fully optional. No-op when the LiteLLM SDK
    is not installed.

    A ``Router`` is required (not ``litellm.model_list`` + plain
    ``litellm.completion``): the plain completion entrypoint cannot resolve
    custom model names, while the Router resolves the alias to its
    deployments.
    """
    global _ROUTER
    if not _llm_stack_available():
        return
    import litellm

    def _params(model: str, api_key: str) -> dict:
        params: dict = {"model": model}
        if api_key:
            params["api_key"] = api_key
        return params

    model_list = [
        {
            "model_name": LLM_ALIAS,
            "litellm_params": _params(
                settings.PRIMARY_LLM_MODEL, settings.MISTRAL_API_KEY
            ),
        },
    ]
    fallbacks: list[dict] = []
    if settings.GROQ_API_KEY:
        fallback_name = "meta-pro-llm-groq"
        model_list.append(
            {
                "model_name": fallback_name,
                "litellm_params": _params(
                    settings.FALLBACK_LLM_MODEL, settings.GROQ_API_KEY
                ),
            }
        )
        fallbacks.append({LLM_ALIAS: [fallback_name]})

    _ROUTER = litellm.Router(
        model_list=model_list,
        fallbacks=fallbacks,
        num_retries=0,  # tenacity owns the retry policy in this app
        # Pull a deployment out of rotation once it fails ``allowed_fails``
        # times within a minute — LiteLLM cools a deployment down on 429s
        # immediately. A rate-limited Mistral is therefore not hammered by
        # the rest of the run: calls route to the fallback (when configured)
        # or surface fast to the app-level breaker. The duration mirrors
        # the app-level ``BREAKER_COOLDOWN_SECONDS``.
        allowed_fails=2,
        cooldown_time=settings.BREAKER_COOLDOWN_SECONDS,
    )


if _llm_stack_available():
    _configure_litellm_router()


def _structured_completion(
    prompt: str,
    response_model: type[BaseModel],
    model: str = LLM_ALIAS,
) -> BaseModel:
    """Run a single structured completion via Instructor over LiteLLM."""
    import instructor

    if _ROUTER is None:
        raise LLMUnavailableError(
            "LLM provider stack (instructor/litellm) is unavailable — "
            "degrading to deterministic placeholders"
        )

    client = instructor.from_litellm(_ROUTER.completion)
    _pace_call()  # stay under the provider's requests-per-minute quota
    try:
        return client.create(
            model=model,
            response_model=response_model,
            messages=[{"role": "user", "content": prompt}],
            max_retries=0,  # tenacity owns retries here
            strict=False,  # broadest provider compat (Mistral/Groq via LiteLLM)
            temperature=0.2,
        )
    except Exception as exc:
        # Provider errors (429 rate limits, 5xx, timeouts, invalid
        # responses) must degrade the pipeline node, not crash the run.
        # Log the real cause so the server terminal shows why a node
        # degraded (not just the frontend warning banner). Rate limits
        # additionally widen the pacing window for the rest of the run
        # (``_note_rate_limited``) so the provider gets room to recover.
        if _is_rate_limit(exc):
            _note_rate_limited(_extract_retry_after(exc))
        logger.warning("LLM provider call failed: %s", exc)
        raise ProviderUnavailableError(
            f"LLM provider call failed: {exc}"
        ) from exc


def _call_with_retries(fn: Callable[[], T]) -> T:
    """Apply the shared LLM retry policy to a zero-arg callable."""
    return LLM_RETRY(lambda: fn())


def call_llm_with_resilience(
    prompt: str,
    response_model: type[BaseModel],
    chaos_flag: ChaosInjectionFlag | None = None,
) -> BaseModel:
    """Structured LLM call with tenacity retries + LiteLLM provider fallback.

    The ``meta-pro-llm`` alias is resolved by LiteLLM to Mistral with an
    automatic Groq failover; that failover engages on real provider errors,
    while the retry policy below handles transient failures.

    Provider failures (rate limits, 5xx, timeouts) are retried up to 3
    times with exponential backoff, then surfaced as
    :class:`ProviderUnavailableError` (a :class:`SimulatedAPIError`) so the
    graph degrades that node to deterministic placeholders instead of
    failing the run. After repeated consecutive failures a short circuit
    breaker fast-fails the remaining nodes for the rest of the run.

    Chaos modes (mirror ``MetaProState["chaos_injection_flag"]``):
    - ``"API_FAILURE"``: raise :class:`SimulatedAPIError` (a 500) on the first
      two attempts so the exponential-backoff retry path fires before
      succeeding.
    - ``"CORRUPT_SCHEMA"``: after a successful completion, raise
      :class:`SchemaValidationError` to model an invalid payload at worker
      handoff and exercise supervisor validation recovery.
    """
    if not _llm_stack_available():
        raise LLMUnavailableError(
            "LLM provider stack (instructor/litellm) is not installed — "
            "degrading to deterministic placeholders"
        )

    # Circuit-breaker check *before* the retry loop: while the provider is
    # on cooldown, every node degrades instantly instead of burning tenacity
    # backoff sleeps (which would let the cooldown lapse mid-run and re-hit
    # a rate-limited provider). Chaos runs bypass the breaker so their
    # retry-then-succeed scenarios are exercised regardless of global state.
    global _breaker_tripped_at
    if chaos_flag is None and _breaker_tripped_at is not None:
        if time.monotonic() - _breaker_tripped_at < settings.BREAKER_COOLDOWN_SECONDS:
            raise ProviderUnavailableError(
                "LLM provider on cooldown after repeated failures — "
                "degrading to deterministic placeholders"
            )
        # Cooldown elapsed: re-arm the provider and try it for real.
        _breaker_tripped_at = None

    attempts = {"n": 0}

    def _attempt() -> BaseModel:
        attempts["n"] += 1
        if chaos_flag == "API_FAILURE" and attempts["n"] < 3:
            raise SimulatedAPIError(
                f"chaos API_FAILURE (attempt {attempts['n']}/3): "
                "simulated 500 Internal Server Error"
            )
        global _breaker_failures, _breaker_tripped_at
        try:
            result = _structured_completion(prompt, response_model)
        except Exception:
            _breaker_failures += 1
            if _breaker_failures >= _BREAKER_LIMIT:
                _breaker_tripped_at = time.monotonic()
                _breaker_failures = 0
            raise
        _breaker_failures = 0
        return result

    result = _call_with_retries(_attempt)

    if chaos_flag == "CORRUPT_SCHEMA":
        raise SchemaValidationError(
            "chaos CORRUPT_SCHEMA: invalid payload at worker handoff"
        )
    return result


def breaker_status() -> dict[str, Any]:
    """Snapshot of the circuit-breaker + pacing state (for ``/api/health``).

    Lets operators (and the frontend) see whether the provider is being
    rate-limited, how long remains on the cooldown, and the effective
    pacing interval. Reads are best-effort without locking the breaker
    globals — consistent with the single-user, non-atomic design of the
    breaker itself.
    """
    if _breaker_tripped_at is None:
        remaining = 0.0
    else:
        remaining = max(
            0.0,
            settings.BREAKER_COOLDOWN_SECONDS
            - (time.monotonic() - _breaker_tripped_at),
        )
    interval = _effective_pacing_interval()
    return {
        "circuit_breaker": {
            "state": "open" if remaining > 0 else "closed",
            "tripped": remaining > 0,
            "remaining_cooldown_seconds": round(remaining, 1),
            "cooldown_seconds": settings.BREAKER_COOLDOWN_SECONDS,
        },
        "pacing": {
            "min_interval_seconds": settings.MIN_LLM_INTERVAL_SECONDS,
            "boost_seconds": round(
                max(0.0, interval - settings.MIN_LLM_INTERVAL_SECONDS), 1
            ),
            "effective_interval_seconds": round(interval, 1),
        },
    }
