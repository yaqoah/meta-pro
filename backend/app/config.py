"""Application configuration loaded from environment variables / ``.env``."""

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Default comma-separated browser origins for ``ALLOWED_ORIGINS`` (used in
#: production; development mode allows a wildcard origin instead).
DEFAULT_ALLOWED_ORIGINS = "http://localhost:5173,http://localhost:3000"


class Settings(BaseSettings):
    """Central runtime configuration for Meta-Pro.

    Values are read from the environment first, then from ``.env`` in the
    working directory (see ``.env.example`` for the full list).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Deployment environment --------------------------------------------
    # "development" (default): permissive CORS wildcard, no startup checks —
    # ideal for local / Codespaces where forwarded ports use arbitrary origins.
    # "production": strict startup checks (DATABASE_URL + MISTRAL_API_KEY are
    # mandatory) and CORS restricted to the explicit ALLOWED_ORIGINS list.
    ENVIRONMENT: Literal["development", "production"] = "development"

    # --- Provider API keys ------------------------------------------------
    # MISTRAL_API_KEY powers the primary LLM (instructor / litellm) and media
    # transcription (Voxtral speech-to-text) — see tools/ingestion.py.
    MISTRAL_API_KEY: str = ""
    # GROQ_API_KEY is optional: it only enables the emergency LLM fallback
    # (see resilience.py). No Groq key is required to run or to transcribe.
    GROQ_API_KEY: str = ""
    # Mistral Voxtral transcription model (see tools/ingestion.py). Pin an
    # explicit version (e.g. "voxtral-mini-2602") for reproducibility.
    MISTRAL_TRANSCRIPTION_MODEL: str = "voxtral-mini-latest"

    # --- LLM routing (LiteLLM failover group: primary → fallback) ---------
    PRIMARY_LLM_MODEL: str = "mistral/mistral-large-latest"
    FALLBACK_LLM_MODEL: str = "groq/llama-3.3-70b-versatile"

    # --- Infrastructure ---------------------------------------------------
    # Empty by default so the app runs with **zero external services** —
    # ideal for GitHub Codespaces / low-RAM machines where Docker is not
    # running. With no DATABASE_URL the backend auto-degrades to a
    # zero-dependency SQLite file (see CHECKPOINT_SQLITE_URL) and finally to
    # LangGraph's in-memory ``MemorySaver``. Set DATABASE_URL to a Supabase
    # Supavisor connection string (see ``.env.example`` — no local Docker
    # Postgres is provisioned) to opt into persistent Postgres checkpointing.
    # NOTE: in ``ENVIRONMENT=production`` a missing DATABASE_URL is a hard
    # startup error (see ``_production_startup_checks``) — the in-memory /
    # SQLite fallbacks are development conveniences only.
    DATABASE_URL: str = ""
    REDIS_URL: str = ""

    # SQLite checkpoint fallback used when DATABASE_URL is unset (or its
    # database is unreachable). ``SqliteSaver`` from the optional
    # ``langgraph-checkpoint-sqlite`` package; if that package is not
    # installed the backend falls back to ``MemorySaver`` instead.
    CHECKPOINT_SQLITE_URL: str = "sqlite:///./meta_pro.db"

    # --- Runtime guardrails ------------------------------------------------
    MAX_STEPS: int = 10

    # --- Resilience / rate limiting ----------------------------------------
    # Minimum seconds between LLM provider calls. One run fires ~13
    # sequential calls, so pacing keeps a single-user server under a
    # provider's requests-per-minute quota (Mistral's free tier is ~60 RPM
    # with tight per-minute token ceilings) — runs get real content instead
    # of rate-limited placeholders. 0 disables pacing.
    MIN_LLM_INTERVAL_SECONDS: float = 15.0
    # Upper bound (seconds) for honouring a provider's ``Retry-After`` hint
    # before retrying a rate-limited call. Prevents a single retry from
    # stalling the pipeline indefinitely.
    MAX_RETRY_AFTER_SECONDS: float = 60.0
    # Seconds a failed provider is kept on cooldown (shared by the app-level
    # circuit breaker AND the LiteLLM Router deployment cooldown). While
    # tripped, further LLM calls fast-fail so a rate-limited run degrades
    # quickly instead of burning backoff sleeps.
    BREAKER_COOLDOWN_SECONDS: float = 120.0

    # --- API / CORS ----------------------------------------------------------
    # Comma-separated browser origins allowed when ``ENVIRONMENT=production``
    # (e.g. "https://app.vercel.app,https://staging.vercel.app"). In
    # development the API serves a wildcard origin instead — see
    # ``cors_origins`` / ``cors_allow_credentials``.
    ALLOWED_ORIGINS: str = DEFAULT_ALLOWED_ORIGINS

    # ------------------------------------------------------------------
    # Derived CORS configuration
    # ------------------------------------------------------------------
    @property
    def cors_origins(self) -> list[str]:
        """Browser origins allowed by CORS.

        - Development: wildcard ``["*"]`` — Codespaces, forwarded ports and
          local tooling can call the API from any origin.
        - Production: the explicit comma-separated ``ALLOWED_ORIGINS`` list —
          set this to your deployed Vercel frontend domain(s).
        """
        if self.ENVIRONMENT != "production":
            return ["*"]
        return [
            origin.strip()
            for origin in self.ALLOWED_ORIGINS.split(",")
            if origin.strip()
        ]

    @property
    def cors_allow_credentials(self) -> bool:
        """Whether the ``Access-Control-Allow-Credentials`` header is sent.

        Browsers reject that header together with a wildcard
        ``Access-Control-Allow-Origin: *``, so credentials are disabled in
        development (wildcard) and enabled in production (explicit origins).
        """
        return "*" not in self.cors_origins

    @model_validator(mode="after")
    def _production_startup_checks(self) -> "Settings":
        """Fail fast with an explicit error in production when required
        configuration is missing — never silently degrade to the in-memory /
        SQLite development fallbacks in ``ENVIRONMENT=production``."""
        if self.ENVIRONMENT == "production":
            missing = [
                name
                for name, value in (
                    ("DATABASE_URL (Supabase Postgres)", self.DATABASE_URL),
                    ("MISTRAL_API_KEY", self.MISTRAL_API_KEY),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    "Production startup check failed — refusing to start: "
                    "missing required environment variable(s): "
                    + ", ".join(missing)
                    + ". Set them in the Render dashboard / render.yaml "
                    "(see backend/render.yaml), or run with "
                    "ENVIRONMENT=development for permissive local mode."
                )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance (reads env / ``.env`` once)."""
    return Settings()


settings = get_settings()
