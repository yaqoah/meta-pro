"""Application configuration loaded from environment variables / ``.env``."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    # Allowed browser origins (Vercel frontend + local dev). Override with a
    # JSON array in the environment, e.g. CORS_ORIGINS=["https://app.example.com"].
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
    ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance (reads env / ``.env`` once)."""
    return Settings()


settings = get_settings()
