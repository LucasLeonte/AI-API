"""
conftest.py — root-level pytest configuration.

Sets required environment variables BEFORE any application modules are
imported, so that `pydantic_settings.BaseSettings` can be instantiated
without a real `.env` file during the test run.
"""

import os

# ── Inject test-safe env vars before any app module is imported ───────────────
os.environ.setdefault("LLM_API_KEY", "test-fake-key-not-used-in-unit-tests")
os.environ.setdefault("LLM_MODEL", "gemini-3.1-flash-lite")
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "100/minute")
os.environ.setdefault("MAX_LOG_SIZE_CHARS", "50000")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("ALLOWED_ORIGINS", "*")
