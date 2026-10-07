"""
Integration tests for POST /api/v1/analyze.

All LLM calls are mocked so the test suite runs offline without requiring
a real API key.
"""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.schemas.response import AnalyzeResponse, FailureAnalysis


# ── Shared mock data ───────────────────────────────────────────────────────────

MOCK_ANALYSIS = FailureAnalysis(
    error_category="MissingDependency",
    summary="npm install failed because package.json is absent from the workspace.",
    failing_command_or_step="npm install",
    root_cause_breakdown=[
        "The workflow working-directory defaults to the repo root.",
        "package.json was not committed to the repository.",
        "npm exits with ENOENT -2.",
    ],
    suggested_fix=(
        "Run `npm init -y` locally and commit the generated package.json."
    ),
    patch=None,
    confidence_score=0.93,
)

VALID_PAYLOAD = {
    "ci_environment": "github-actions",
    "log_text": (
        "Run npm install\n"
        "npm ERR! code ENOENT\n"
        "npm ERR! path /home/runner/work/app/package.json\n"
        "npm ERR! errno -2\n"
        "Error: Process completed with exit code 1."
    ),
}


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Provide a TestClient with a real (non-reloaded) app instance."""
    with patch("app.config.settings") as mock_cfg:
        mock_cfg.rate_limit_per_minute = "100/minute"
        mock_cfg.max_log_size_chars = 50_000
        mock_cfg.environment = "development"
        mock_cfg.cors_origins = ["*"]
        mock_cfg.llm_api_key = "fake-key"
        mock_cfg.llm_model = "gemini-3.1-flash-lite"

        import importlib
        import app.main as main_module
        importlib.reload(main_module)

        yield TestClient(main_module.app, raise_server_exceptions=False)


# ── Happy-path tests ───────────────────────────────────────────────────────────

class TestAnalyzeSuccess:
    @patch(
        "app.services.llm_service.analyze",
        new_callable=AsyncMock,
        return_value=MOCK_ANALYSIS,
    )
    def test_valid_request_returns_200(self, _mock: AsyncMock, client: TestClient) -> None:
        resp = client.post("/api/v1/analyze", json=VALID_PAYLOAD)
        assert resp.status_code == 200

    @patch(
        "app.services.llm_service.analyze",
        new_callable=AsyncMock,
        return_value=MOCK_ANALYSIS,
    )
    def test_response_matches_analyze_response_schema(
        self, _mock: AsyncMock, client: TestClient
    ) -> None:
        resp = client.post("/api/v1/analyze", json=VALID_PAYLOAD)
        assert resp.status_code == 200
        # Validate against Pydantic schema (raises on mismatch)
        parsed = AnalyzeResponse(**resp.json())
        assert parsed.status == "success"
        assert parsed.analysis.error_category == "MissingDependency"
        assert parsed.analysis.confidence_score == pytest.approx(0.93)
        assert isinstance(parsed.execution_time_ms, int)
        assert parsed.execution_time_ms >= 0

    @patch(
        "app.services.llm_service.analyze",
        new_callable=AsyncMock,
        return_value=MOCK_ANALYSIS,
    )
    def test_response_has_process_time_header(
        self, _mock: AsyncMock, client: TestClient
    ) -> None:
        resp = client.post("/api/v1/analyze", json=VALID_PAYLOAD)
        assert "x-process-time-ms" in resp.headers

    @patch(
        "app.services.llm_service.analyze",
        new_callable=AsyncMock,
        return_value=MOCK_ANALYSIS,
    )
    def test_all_ci_environments_are_accepted(
        self, _mock: AsyncMock, client: TestClient
    ) -> None:
        for env in ("github-actions", "gitlab-ci", "docker-build", "generic"):
            payload = {**VALID_PAYLOAD, "ci_environment": env}
            resp = client.post("/api/v1/analyze", json=payload)
            assert resp.status_code == 200, (
                f"Environment '{env}' returned {resp.status_code}: {resp.text}"
            )


# ── Validation / rejection tests ───────────────────────────────────────────────

class TestAnalyzeValidationErrors:
    def test_missing_log_text_returns_422(self, client: TestClient) -> None:
        resp = client.post("/api/v1/analyze", json={"ci_environment": "generic"})
        assert resp.status_code == 422

    def test_empty_log_text_returns_422(self, client: TestClient) -> None:
        resp = client.post("/api/v1/analyze", json={"log_text": ""})
        assert resp.status_code == 422

    def test_too_short_log_text_returns_422(self, client: TestClient) -> None:
        # min_length is 10; 9 chars should fail
        resp = client.post(
            "/api/v1/analyze",
            json={"log_text": "short"},
        )
        assert resp.status_code == 422

    def test_invalid_ci_environment_returns_422(self, client: TestClient) -> None:
        payload = {**VALID_PAYLOAD, "ci_environment": "jenkins"}
        resp = client.post("/api/v1/analyze", json=payload)
        assert resp.status_code == 422

    def test_oversized_log_text_returns_422_or_413(self, client: TestClient) -> None:
        # Pydantic max_length=50000 will catch this before our explicit guard
        oversized_payload = {**VALID_PAYLOAD, "log_text": "a" * 50_001}
        resp = client.post("/api/v1/analyze", json=oversized_payload)
        assert resp.status_code in (413, 422)

    def test_empty_json_body_returns_422(self, client: TestClient) -> None:
        resp = client.post("/api/v1/analyze", json={})
        assert resp.status_code == 422

    def test_non_json_body_returns_422(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/analyze",
            content=b"not-json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422


# ── Upstream LLM error propagation tests ──────────────────────────────────────

class TestAnalyzeLLMErrors:
    @patch(
        "app.services.llm_service.analyze",
        new_callable=AsyncMock,
        side_effect=__import__("fastapi").HTTPException(status_code=502, detail="LLM error"),
    )
    def test_llm_502_is_propagated(self, _mock: AsyncMock, client: TestClient) -> None:
        resp = client.post("/api/v1/analyze", json=VALID_PAYLOAD)
        assert resp.status_code == 502

    @patch(
        "app.services.llm_service.analyze",
        new_callable=AsyncMock,
        side_effect=__import__("fastapi").HTTPException(status_code=504, detail="Timeout"),
    )
    def test_llm_504_is_propagated(self, _mock: AsyncMock, client: TestClient) -> None:
        resp = client.post("/api/v1/analyze", json=VALID_PAYLOAD)
        assert resp.status_code == 504


# ── Health endpoint ────────────────────────────────────────────────────────────

class TestHealthEndpoint:
    def test_health_returns_200(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_response_structure(self, client: TestClient) -> None:
        resp = client.get("/health")
        body = resp.json()
        assert body["status"] == "healthy"
        assert "timestamp" in body
        assert "version" in body
