"""Application configuration via environment variables using Pydantic Settings."""

from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All configuration is read from environment variables (or a .env file).
    Sensitive values such as LLM_API_KEY are never included in logs or responses.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── LLM Provider ─────────────────────────────────────────────────────────
    llm_api_key: str = Field(
        ...,
        description="API key for the LLM provider (Google Gemini or OpenAI).",
    )
    llm_model: str = Field(
        default="gemini-2.5-flash",
        description="Model identifier to use for log analysis.",
    )

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    rate_limit_per_minute: str = Field(
        default="10/minute",
        description="SlowAPI rate-limit string, e.g. '10/minute'.",
    )

    # ── Request Constraints ───────────────────────────────────────────────────
    max_log_size_chars: int = Field(
        default=50_000,
        ge=1,
        description="Maximum characters accepted in a single log payload.",
    )

    # ── Runtime ───────────────────────────────────────────────────────────────
    environment: Literal["development", "production"] = Field(
        default="development",
        description="Deployment environment; affects logging verbosity.",
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    allowed_origins: str = Field(
        default="*",
        description="Comma-separated list of CORS allowed origins, or '*' for all.",
    )

    @property
    def cors_origins(self) -> list[str]:
        """Parse ALLOWED_ORIGINS into a list."""
        return [o.strip() for o in self.allowed_origins.split(",")]


# Singleton instance — import this everywhere
settings = Settings()  # type: ignore[call-arg]
