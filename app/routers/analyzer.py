"""Analyzer router — POST /api/v1/analyze."""

import logging
import time

from fastapi import APIRouter, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.schemas.request import AnalyzeRequest
from app.schemas.response import AnalyzeResponse
from app.services import llm_service
from app.services.sanitizer import sanitize_log

logger = logging.getLogger(__name__)

# The limiter instance is shared with main.py via the app state.
# We reference it here only to apply the @limiter.limit decorator.
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/api/v1", tags=["Analyzer"])


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    summary="Analyze CI/CD Failure Log",
    description=(
        "Submit a raw CI/CD build or test failure log and receive a structured "
        "JSON diagnosis with root-cause breakdown and an optional auto-fix patch.\n\n"
        "**Security notes:**\n"
        "- Logs are sanitised server-side to redact secrets before forwarding to the LLM.\n"
        "- Requests are rate-limited per IP address.\n"
        "- Log bodies exceeding `MAX_LOG_SIZE_CHARS` are truncated (tail-preserved)."
    ),
    responses={
        200: {"description": "Successful diagnosis."},
        400: {"description": "Validation error — request payload is malformed."},
        413: {"description": "Log payload exceeds the configured size limit."},
        422: {"description": "Unprocessable entity — Pydantic validation failed."},
        429: {"description": "Rate limit exceeded."},
        502: {"description": "LLM provider returned an error or malformed response."},
        504: {"description": "LLM provider timed out."},
    },
)
@limiter.limit(settings.rate_limit_per_minute)
async def analyze_log(
    request: Request,
    payload: AnalyzeRequest,
) -> AnalyzeResponse:
    """
    Analyze a CI/CD failure log using a large language model.

    Processing pipeline:
    1. Validate request via Pydantic (automatic).
    2. Sanitize log — redact secrets and truncate if oversized.
    3. Forward sanitised log + CI environment context to the LLM.
    4. Parse and validate LLM JSON response against ``FailureAnalysis`` schema.
    5. Return ``AnalyzeResponse`` with timing metadata.
    """
    start_ms = time.monotonic()

    # ── Guard: explicit size check (belt-and-suspenders beyond Pydantic) ──────
    if len(payload.log_text) > settings.max_log_size_chars:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Log payload exceeds the maximum allowed size of "
                f"{settings.max_log_size_chars} characters."
            ),
        )

    # ── Step 1: Sanitize ──────────────────────────────────────────────────────
    sanitized = sanitize_log(payload.log_text)
    logger.info(
        "Sanitized log for %s (original=%d chars, sanitized=%d chars)",
        payload.ci_environment,
        len(payload.log_text),
        len(sanitized),
    )

    # ── Step 2: Analyze ───────────────────────────────────────────────────────
    analysis = await llm_service.analyze(
        ci_environment=payload.ci_environment.value,
        sanitized_log=sanitized,
    )

    elapsed_ms = int((time.monotonic() - start_ms) * 1000)

    return AnalyzeResponse(
        status="success",
        analysis=analysis,
        execution_time_ms=elapsed_ms,
    )
