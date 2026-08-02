"""Media ingestion tool for Meta-Pro.

Transcribes audio/video uploads via Mistral's Voxtral speech-to-text API
(``voxtral-mini-latest`` by default) and gracefully falls back to raw text
input when no media is provided or transcription fails — the result is
seeded into ``MetaProState["transcript_text"]``.

Transcription uses the same ``MISTRAL_API_KEY`` as the primary LLM, so no
Groq API key is required anywhere in the pipeline.
"""

from __future__ import annotations

import logging

from app.config import settings
from app.schemas import (
    ChaosInjectionFlag,
    MetaProState,
    StrategicAngle,
    initial_state,
)

logger = logging.getLogger(__name__)

# Hard fallback used when ``MISTRAL_TRANSCRIPTION_MODEL`` is empty/unset.
DEFAULT_TRANSCRIPTION_MODEL = "voxtral-mini-latest"

# Formats accepted by the Mistral Voxtral transcription API (audio tracks are
# extracted from video containers like mp4 by the service).
SUPPORTED_FORMATS = ("flac", "m4a", "mp3", "mp4", "mpeg", "mpga", "ogg", "wav", "webm")

_MIME_BY_EXT = {
    "mp3": "audio/mpeg",
    "mp4": "video/mp4",
    "mpeg": "audio/mpeg",
    "mpga": "audio/mpeg",
    "m4a": "audio/mp4",
    "wav": "audio/wav",
    "webm": "audio/webm",
    "ogg": "audio/ogg",
    "flac": "audio/flac",
}


class TranscriptionError(Exception):
    """Raised when media transcription is unavailable or fails."""


def _guess_mime(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return _MIME_BY_EXT.get(ext, "application/octet-stream")


def transcribe_media(
    file_bytes: bytes,
    filename: str = "audio.mp3",
    content_type: str | None = None,
    model: str | None = None,
) -> str:
    """Transcribe an audio/video upload via Mistral's Voxtral API.

    Uses the official ``mistralai`` SDK (``client.audio.transcriptions``)
    with the same ``MISTRAL_API_KEY`` used for LLM routing, so no separate
    transcription key is needed. Returns the raw transcript text. Raises
    :class:`TranscriptionError` when no API key is configured or the provider
    call fails.
    """
    if not settings.MISTRAL_API_KEY:
        raise TranscriptionError(
            "MISTRAL_API_KEY is not set — cannot transcribe media"
        )
    model = model or settings.MISTRAL_TRANSCRIPTION_MODEL or DEFAULT_TRANSCRIPTION_MODEL
    # Lazy import so the app boots (and degrades to raw-text input) in
    # environments where the mistralai SDK is not installed.
    try:
        # v2 SDK exposes the client at ``mistralai.client`` (the top-level
        # ``mistralai`` namespace re-exports nothing).
        from mistralai.client import Mistral
    except ImportError:
        raise TranscriptionError(
            "The 'mistralai' package is not installed — cannot transcribe media"
        ) from None
    client = Mistral(api_key=settings.MISTRAL_API_KEY)
    response = client.audio.transcriptions.complete(
        model=model,
        file={
            "file_name": filename,
            "content": file_bytes,
            "content_type": content_type or _guess_mime(filename),
        },
    )
    return response.text.strip()


def ingest_source(
    transcript_text: str = "",
    file_bytes: bytes | None = None,
    filename: str | None = None,
    content_type: str | None = None,
) -> str:
    """Return the transcript text to feed into ``MetaProState``.

    Prefers transcribing uploaded media; on any failure (missing API key,
    provider error, empty file) it degrades gracefully to raw
    ``transcript_text``.
    """
    if file_bytes:
        try:
            return transcribe_media(
                file_bytes,
                filename=filename or "audio.mp3",
                content_type=content_type,
            )
        except Exception as exc:  # graceful degradation is the whole point
            logger.warning(
                "Media transcription failed; falling back to raw text: %s", exc
            )
    text = (transcript_text or "").strip()
    if not text:
        raise TranscriptionError("No media file or transcript text was provided")
    return text


def build_initial_state(
    transcript_text: str = "",
    file_bytes: bytes | None = None,
    filename: str | None = None,
    content_type: str | None = None,
    focus_direction: str = "",
    strategic_angle: StrategicAngle = StrategicAngle.TECHNICAL,
    chaos_injection_flag: ChaosInjectionFlag | None = None,
) -> MetaProState:
    """Build a :class:`MetaProState` seeded via :func:`ingest_source`."""
    ingested = ingest_source(
        transcript_text,
        file_bytes=file_bytes,
        filename=filename,
        content_type=content_type,
    )
    return initial_state(
        transcript_text=ingested,
        focus_direction=focus_direction,
        strategic_angle=strategic_angle,
        chaos_injection_flag=chaos_injection_flag,
    )
