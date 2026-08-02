"""Pydantic schemas & state contracts for Meta-Pro.

Every agent node validates its inputs/outputs against these models before
touching the shared graph state, enforcing contract-first validation.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Literal, Optional

# typing_extensions.TypedDict required on Python < 3.12 for pydantic to
# build schemas from the state TypedDict (e.g. FastAPI response models).
from typing_extensions import TypedDict

from pydantic import BaseModel, Field


class PlatformType(str, Enum):
    """Social platforms Meta-Pro can target."""

    LINKEDIN = "linkedin"
    X_THREAD = "x_thread"
    MEDIUM = "medium"


class StrategicAngle(str, Enum):
    """High-level positioning angles for the content."""

    RECRUITER = "recruiter"
    TECHNICAL = "technical"
    FOUNDER = "founder"
    CONTRARIAN = "contrarian"


class HookOption(BaseModel):
    """A single hook option generated for a platform."""

    id: str = Field(..., description="Stable identifier for the hook, e.g. 'h1'")
    style: str = Field(..., description="Hook style, e.g. 'contrarian', 'stat-led'")
    headline: str = Field(..., description="The hook headline text")
    reasoning: str = Field(..., description="Why this hook should perform well")


class PlatformStrategyOutput(BaseModel):
    """Full strategy output produced per platform by the strategy agent."""

    platform: PlatformType
    hooks: List[HookOption] = Field(
        ...,
        min_length=3,
        max_length=3,
        description="Exactly 3 hook options per platform",
    )
    algorithm_checklist: List[str] = Field(
        default_factory=list,
        description="Platform-algorithm levers to honor (line breaks, CTAs, ...)",
    )
    visual_diagram_mermaid: str = Field(
        default="",
        description="Valid dark-mode Mermaid.js flowchart string",
    )
    claude_meta_prompt: str = Field(
        default="",
        description="Stuffed, structured prompt ready for Claude 3.5 Sonnet",
    )


class SupervisorRoute(BaseModel):
    """Routing decision emitted by the supervisor node."""

    next_worker: Literal[
        "strategy_agent", "visual_agent", "prompt_builder", "FINISH"
    ]
    reasoning: str


# Values chaos-engineering mode may inject to exercise resilience paths.
ChaosInjectionFlag = Literal["API_FAILURE", "CORRUPT_SCHEMA", "INFINITE_LOOP"]


class MetaProState(TypedDict, total=False):
    """Shared state threaded through the LangGraph pipeline.

    ``total=False``: nodes progressively fill channels; ``initial_state()``
    seeds the common defaults.
    """

    transcript_text: str
    focus_direction: str
    strategic_angle: StrategicAngle
    active_platform: PlatformType
    strategy_results: Dict[str, PlatformStrategyOutput]
    supervisor_route: SupervisorRoute  # routing channel written by the supervisor node
    step_count: int
    state_hashes: List[str]  # digests of prior states — used for cycle detection
    chaos_injection_flag: Optional[ChaosInjectionFlag]
    error_log: List[str]


def initial_state(
    transcript_text: str = "",
    focus_direction: str = "",
    strategic_angle: StrategicAngle = StrategicAngle.TECHNICAL,
    chaos_injection_flag: Optional[ChaosInjectionFlag] = None,
) -> MetaProState:
    """Build a fresh, valid MetaProState for a new graph run."""
    return {
        "transcript_text": transcript_text,
        "focus_direction": focus_direction,
        "strategic_angle": strategic_angle,
        "strategy_results": {},
        "step_count": 0,
        "state_hashes": [],
        "chaos_injection_flag": chaos_injection_flag,
        "error_log": [],
    }
