"""FastAPI application & SSE streaming server for Meta Pro.

Endpoints:
- ``POST /api/generate/stream`` — multipart (media upload and/or raw text),
  streams per-node progress events over Server-Sent Events while the bounded
  LangGraph workflow runs via ``astream_events(..., version="v2")``.
- ``GET  /api/health`` — API health, database status and active configuration.
- ``GET  /api/history/{thread_id}`` — checkpointed state history for a thread.
- Legacy: ``GET /health`` (liveness) and ``POST /run`` (non-streaming invoke).
"""

from __future__ import annotations

import json
import logging
import uuid
from enum import Enum
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel, Field

from app.config import settings
from app.graph import NODE_NAMES, workflow
from app.schemas import (
    ChaosInjectionFlag,
    MetaProState,
    PlatformType,
    StrategicAngle,
    initial_state,
)
from app.tools.ingestion import TranscriptionError, build_initial_state

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Meta Pro API",
    description="Contract-first content strategy agent (transcript → platform playbook), streamed live over SSE.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _json_default(obj):
    """JSON fallback for pydantic models / enums in graph state payloads."""
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, Enum):
        return obj.value
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _sse_message(event_type: str, payload: dict) -> str:
    """Format one Server-Sent Event (single-line ``data`` for safety)."""
    data = json.dumps(payload, default=_json_default)
    return f"event: {event_type}\ndata: {data}\n\n"


# ---------------------------------------------------------------------------
# SSE streaming
# ---------------------------------------------------------------------------


async def _stream_run(state: MetaProState, thread_id: str, source: str) -> AsyncIterator[str]:
    """Run the workflow and stream per-node progress + the final payload."""
    config = {"configurable": {"thread_id": thread_id}}
    yield _sse_message(
        "start",
        {
            "type": "start",
            "step": "00",
            "thread_id": thread_id,
            "status": "active",
            "source": source,
        },
    )

    step = 0
    final_state: dict | None = None
    try:
        async for event in workflow.astream_events(state, config, version="v2"):
            name = event.get("name")
            if name == "LangGraph":
                # Graph-level end event carries the final merged state.
                if event["event"] == "on_chain_end":
                    final_state = (event.get("data") or {}).get("output")
                continue
            if name not in NODE_NAMES:
                continue  # skip conditional-edge and nested run events
            if event["event"] == "on_chain_start":
                step += 1
                yield _sse_message(
                    "step",
                    {"type": "step", "step": f"{step:02d}", "node": name, "status": "active"},
                )
            elif event["event"] == "on_chain_end":
                yield _sse_message(
                    "step",
                    {"type": "step", "step": f"{step:02d}", "node": name, "status": "done"},
                )
    except Exception as exc:
        logger.exception("workflow streaming failed")
        yield _sse_message(
            "error",
            {"type": "error", "status": "error", "thread_id": thread_id, "detail": str(exc)},
        )
        return

    if final_state is None:
        # Fallback: read the latest checkpoint for the thread.
        tup = workflow.checkpointer.get_tuple(config)
        if tup is not None:
            final_state = tup.checkpoint["channel_values"]

    try:
        yield _sse_message(
            "result",
            {
                "type": "result",
                "status": "done" if final_state is not None else "terminated",
                "thread_id": thread_id,
                "step_count": (final_state or {}).get("step_count"),
                "error_log": (final_state or {}).get("error_log", []),
                "final_state": final_state,
            },
        )
    except Exception as exc:  # serialization failure — never crash mid-stream
        logger.exception("failed to serialize final state")
        yield _sse_message(
            "error",
            {
                "type": "error",
                "status": "error",
                "thread_id": thread_id,
                "detail": str(exc),
            },
        )


@app.post("/api/generate/stream")
async def generate_stream(
    transcript_text: str = Form(""),
    focus_direction: str = Form(""),
    strategic_angle: StrategicAngle = Form(StrategicAngle.TECHNICAL),
    active_platform: PlatformType | None = Form(None),
    chaos_injection_flag: ChaosInjectionFlag | None = Form(None),
    thread_id: str | None = Form(None),
    media: UploadFile | None = File(None),
) -> StreamingResponse:
    """Stream the supervisor pipeline as SSE.

    Provide either ``media`` (audio/video upload, transcribed via Groq
    Whisper with raw-text fallback) or ``transcript_text``. Reusing a
    ``thread_id`` rehydrates the run from the checkpointed state.
    """
    tid = thread_id or uuid.uuid4().hex
    media_bytes = await media.read() if media else None
    try:
        state = build_initial_state(
            transcript_text=transcript_text,
            file_bytes=media_bytes,
            filename=media.filename if media else None,
            content_type=media.content_type if media else None,
            focus_direction=focus_direction,
            strategic_angle=strategic_angle,
            chaos_injection_flag=chaos_injection_flag,
        )
    except TranscriptionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if active_platform is not None:
        state["active_platform"] = active_platform

    return StreamingResponse(
        _stream_run(state, tid, source="media" if media_bytes else "text"),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Utility endpoints
# ---------------------------------------------------------------------------


@app.get("/api/health")
def api_health() -> dict:
    """API health, database connection status and active configuration."""
    checkpointer = workflow.checkpointer
    backend = type(checkpointer).__name__
    # Only the in-memory checkpointer is non-persistent; SQLite and Postgres
    # both count as "connected". isinstance() against core langgraph avoids
    # any dependency on the optional checkpointer SDKs.
    is_memory = isinstance(checkpointer, MemorySaver)
    return {
        "status": "ok",
        "app": app.title,
        "version": app.version,
        "database": {
            "backend": backend,
            "status": (
                "in-memory fallback (non-persistent)"
                if is_memory
                else "connected"
            ),
        },
        "config": {
            "max_steps": settings.MAX_STEPS,
            "primary_llm_model": settings.PRIMARY_LLM_MODEL,
            "fallback_llm_model": settings.FALLBACK_LLM_MODEL,
            "mistral_api_key": "set" if settings.MISTRAL_API_KEY else "unset",
            "groq_api_key": "set" if settings.GROQ_API_KEY else "unset",
            "cors_origins": settings.CORS_ORIGINS,
        },
    }


@app.get("/api/history/{thread_id}")
def thread_history(thread_id: str) -> dict:
    """Checkpointed state history for a given thread (checkpointer-backed)."""
    checkpointer = workflow.checkpointer
    config = {"configurable": {"thread_id": thread_id}}
    checkpoints: list[dict] = []
    for tup in checkpointer.list(config, limit=50):
        metadata = tup.metadata or {}
        cp_config = (tup.config or {}).get("configurable", {})
        checkpoints.append(
            {
                "checkpoint_id": cp_config.get("checkpoint_id"),
                "step": metadata.get("step"),
                "source": metadata.get("source"),
                "state": tup.checkpoint["channel_values"],
            }
        )
    return {
        "thread_id": thread_id,
        "checkpointer": type(checkpointer).__name__,
        "checkpoints": checkpoints,
    }


# ---------------------------------------------------------------------------
# Legacy endpoints (kept for compatibility)
# ---------------------------------------------------------------------------


class RunRequest(BaseModel):
    transcript_text: str
    focus_direction: str = ""
    strategic_angle: StrategicAngle = StrategicAngle.TECHNICAL
    chaos_injection_flag: ChaosInjectionFlag | None = None
    thread_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        description="Checkpoint thread id — reuse it to resume a run, omit it for a fresh run",
    )


class RunResponse(BaseModel):
    final_state: MetaProState


@app.get("/health")
def health() -> dict:
    """Liveness probe."""
    return {"status": "ok", "max_steps": settings.MAX_STEPS}


@app.post("/run", response_model=RunResponse)
def run_graph(payload: RunRequest) -> RunResponse:
    """Non-streaming convenience: execute the bounded pipeline and return state."""
    state = initial_state(
        transcript_text=payload.transcript_text,
        focus_direction=payload.focus_direction,
        strategic_angle=payload.strategic_angle,
        chaos_injection_flag=payload.chaos_injection_flag,
    )
    final_state = workflow.invoke(
        state,
        config={"configurable": {"thread_id": payload.thread_id}},
    )
    return RunResponse(final_state=final_state)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
