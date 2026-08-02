"""Resilience layer for Meta-Pro.

Provides:
- Multi-provider LLM routing via LiteLLM (Mistral primary, Groq fallback)
  with structured output via Instructor (``instructor.from_litellm``).
- Tenacity retry with exponential backoff and a logging hook on retries.
- ``call_llm_with_resilience`` entrypoint with chaos-engineering hooks.
- Step-budget guard (``MAX_STEPS``) and cycle detection via state digests.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Callable, Dict, TypeVar

from pydantic import BaseModel
from tenacity import (
    Retrying,
    before_sleep_log,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings
from app.schemas import ChaosInjectionFlag

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Logical model name resolved by LiteLLM to the [Mistral → Groq] failover group.
LLM_ALIAS = "meta-pro-llm"

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

# Tenacity policy: exponential backoff (multiplier=1, clamped to [2s, 10s]),
# at most 3 attempts, with a WARNING log hook before every retry sleep.
# A Retrying instance (not the @retry decorator factory) so the policy is
# directly inspectable — e.g. ``LLM_RETRY.stop.max_attempt_number``.
LLM_RETRY = Retrying(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


def _configure_litellm_router() -> None:
    """Route ``LLM_ALIAS`` to the primary model with automatic failover.

    Both entries share ``LLM_ALIAS`` as ``model_name``, so LiteLLM treats
    them as one failover group: primary Mistral, falling back to Groq on
    provider errors / timeouts. No-op when the LiteLLM SDK is not installed.
    """
    if not _llm_stack_available():
        return
    import litellm

    def _params(model: str, api_key: str) -> dict:
        params: dict = {"model": model}
        if api_key:
            params["api_key"] = api_key
        return params

    litellm.model_list = [
        {
            "model_name": LLM_ALIAS,
            "litellm_params": _params(
                settings.PRIMARY_LLM_MODEL, settings.MISTRAL_API_KEY
            ),
        },
        {
            "model_name": LLM_ALIAS,
            "litellm_params": _params(
                settings.FALLBACK_LLM_MODEL, settings.GROQ_API_KEY
            ),
        },
    ]


if _llm_stack_available():
    _configure_litellm_router()


def _structured_completion(
    prompt: str,
    response_model: type[BaseModel],
    model: str = LLM_ALIAS,
) -> BaseModel:
    """Run a single structured completion via Instructor over LiteLLM."""
    import instructor
    import litellm

    client = instructor.from_litellm(litellm.completion)
    return client.create(
        model=model,
        response_model=response_model,
        messages=[{"role": "user", "content": prompt}],
        max_retries=0,  # tenacity owns retries here
        strict=False,  # broadest provider compat (Mistral/Groq via LiteLLM)
        temperature=0.2,
    )


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

    attempts = {"n": 0}

    def _attempt() -> BaseModel:
        attempts["n"] += 1
        if chaos_flag == "API_FAILURE" and attempts["n"] < 3:
            raise SimulatedAPIError(
                f"chaos API_FAILURE (attempt {attempts['n']}/3): "
                "simulated 500 Internal Server Error"
            )
        return _structured_completion(prompt, response_model)

    result = _call_with_retries(_attempt)

    if chaos_flag == "CORRUPT_SCHEMA":
        raise SchemaValidationError(
            "chaos CORRUPT_SCHEMA: invalid payload at worker handoff"
        )
    return result
