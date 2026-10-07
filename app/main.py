"""
FastAPI application entry point.

Responsibilities:
- Create and configure the FastAPI application instance.
- Register CORS, SlowAPI rate-limiting, and process-time middleware.
- Mount routers for /health and /api/v1/analyze.
- Provide rich OpenAPI metadata for the /docs UI.
"""

import logging
import time
from collections.abc import Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings
from app.routers import analyzer, health

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.environment == "development" else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── Rate limiter (shared with routers via app.state) ──────────────────────────
limiter = Limiter(key_func=get_remote_address)

# ── FastAPI application ────────────────────────────────────────────────────────
app = FastAPI(
    title="CI/CD Failure Analyzer & Auto-Fix API",
    description=(
        "A production-ready AI microservice that accepts raw CI/CD build / test "
        "failure logs and returns a **structured JSON diagnosis** — including root-"
        "cause breakdown, error category, and optional auto-fix code patches — "
        "powered by Google Gemini.\n\n"
        "**Key features:**\n"
        "- Secret redaction before logs reach the LLM\n"
        "- IP-based rate limiting via SlowAPI\n"
        "- Strict Pydantic v2 request & response validation\n"
        "- Docker-ready with non-root user\n\n"
        "Source code: [github.com/LucasLeonte/AI-API](https://github.com/LucasLeonte/AI-API)"
    ),
    version="1.0.0",
    contact={
        "name": "Lucas Leonte",
        "url": "https://github.com/LucasLeonte/AI-API",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    openapi_tags=[
        {
            "name": "Health",
            "description": "Liveness / readiness probe endpoints.",
        },
        {
            "name": "Analyzer",
            "description": "CI/CD log analysis and auto-fix patch generation.",
        },
    ],
)

# ── Attach limiter to app state (required by SlowAPI) ─────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# ── CORS middleware ────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Process-time middleware ────────────────────────────────────────────────────
@app.middleware("http")
async def add_process_time_header(request: Request, call_next: Callable) -> Response:
    """Measure end-to-end request duration and inject it as a response header."""
    start = time.monotonic()
    response: Response = await call_next(request)
    elapsed_ms = int((time.monotonic() - start) * 1000)
    response.headers["X-Process-Time-Ms"] = str(elapsed_ms)
    return response


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(analyzer.router)

# ── Root redirect hint ────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    """Redirect hint for users hitting the bare root URL."""
    return {
        "message": "CI/CD Failure Analyzer API",
        "docs": "/docs",
        "health": "/health",
        "analyze": "/api/v1/analyze",
    }
