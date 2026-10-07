"""
Rate-limit integration tests — verifies that the SlowAPI limiter returns
HTTP 429 after the configured threshold is exhausted.

The LLM backend is mocked so these tests run fully offline and quickly.
"""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.schemas.response import FailureAnalysis


# ── Shared fixture helpers ─────────────────────────────────────────────────────

MOCK_ANALYSIS = FailureAnalysis(
    error_category="MissingDependency",
    summary="npm install failed because package.json is absent.",
    failing_command_or_step="npm install",
    root_cause_breakdown=["package.json was not committed."],
    suggested_fix="Run npm init -y and commit package.json.",
    patch=None,
    confidence_score=0.95,
)

VALID_PAYLOAD = {
    "ci_environment": "github-actions",
    "log_text": (
        "Run npm install\n"
        "npm ERR! code ENOENT\n"
        "npm ERR! path /home/runner/work/app/package.json\n"
        "Error: Process completed with exit code 1."
    ),
}


def _make_client(rate_limit: str = "3/minute") -> TestClient:
    """
    Build a TestClient with an overridden low rate limit and mocked settings.
    SlowAPI uses an in-memory store per process, so we reset the app each time.
    """
    with patch("app.config.settings") as mock_cfg:
        mock_cfg.rate_limit_per_minute = rate_limit
        mock_cfg.max_log_size_chars = 50_000
        mock_cfg.environment = "development"
        mock_cfg.cors_origins = ["*"]
        mock_cfg.llm_api_key = "fake-key"
        mock_cfg.llm_model = "gemini-3.1-flash-lite"

        # Re-import app *after* patching settings so the limiter picks up the new limit
        import importlib
        import app.main as main_module
        importlib.reload(main_module)

        client = TestClient(main_module.app, raise_server_exceptions=False)
        return client


class TestRateLimiting:
    """Tests that the rate limiter blocks requests beyond the configured threshold."""

    @patch(
        "app.services.llm_service.analyze",
        new_callable=AsyncMock,
        return_value=MOCK_ANALYSIS,
    )
    def test_requests_below_limit_succeed(self, _mock_analyze: AsyncMock) -> None:
        """First N requests (below limit) should all return 200."""
        with patch("app.config.settings") as mock_cfg:
            mock_cfg.rate_limit_per_minute = "5/minute"
            mock_cfg.max_log_size_chars = 50_000
            mock_cfg.environment = "development"
            mock_cfg.cors_origins = ["*"]
            mock_cfg.llm_api_key = "fake-key"
            mock_cfg.llm_model = "gemini-3.1-flash-lite"

            import importlib
            import app.main as main_module
            importlib.reload(main_module)

            client = TestClient(main_module.app, raise_server_exceptions=False)

            for i in range(3):
                resp = client.post("/api/v1/analyze", json=VALID_PAYLOAD)
                assert resp.status_code == 200, (
                    f"Request {i + 1} expected 200, got {resp.status_code}: {resp.text}"
                )

    @patch(
        "app.services.llm_service.analyze",
        new_callable=AsyncMock,
        return_value=MOCK_ANALYSIS,
    )
    def test_requests_exceeding_limit_return_429(self, _mock_analyze: AsyncMock) -> None:
        """After exhausting the rate limit, subsequent requests must return 429."""
        limit = 5

        with patch("app.config.settings") as mock_cfg:
            mock_cfg.rate_limit_per_minute = f"{limit}/minute"
            mock_cfg.max_log_size_chars = 50_000
            mock_cfg.environment = "development"
            mock_cfg.cors_origins = ["*"]
            mock_cfg.llm_api_key = "fake-key"
            mock_cfg.llm_model = "gemini-3.1-flash-lite"

            import importlib
            import app.main as main_module
            importlib.reload(main_module)

            client = TestClient(main_module.app, raise_server_exceptions=False)

            statuses = []
            for _ in range(limit + 5):
                resp = client.post("/api/v1/analyze", json=VALID_PAYLOAD)
                statuses.append(resp.status_code)

        # At least one response after limit exhaustion should be 429
        assert 429 in statuses, (
            f"Expected at least one 429 response, got statuses: {statuses}"
        )

    def test_health_endpoint_not_rate_limited(self) -> None:
        """The /health endpoint must always respond even if analyze is rate-limited."""
        with patch("app.config.settings") as mock_cfg:
            mock_cfg.rate_limit_per_minute = "1/minute"
            mock_cfg.max_log_size_chars = 50_000
            mock_cfg.environment = "development"
            mock_cfg.cors_origins = ["*"]
            mock_cfg.llm_api_key = "fake-key"
            mock_cfg.llm_model = "gemini-3.1-flash-lite"

            import importlib
            import app.main as main_module
            importlib.reload(main_module)

            client = TestClient(main_module.app, raise_server_exceptions=False)

            for _ in range(5):
                resp = client.get("/health")
                assert resp.status_code == 200
