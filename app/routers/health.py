"""Health check router — GET /health."""

from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter(tags=["Health"])

APP_VERSION = "1.0.0"


@router.get(
    "/health",
    summary="Health Check",
    description=(
        "Lightweight liveness probe. Returns `200 OK` with the current UTC "
        "timestamp and application version. Use this endpoint for uptime "
        "monitors and load-balancer health checks."
    ),
    response_description="Service is healthy and ready to accept requests.",
)
async def health_check() -> dict[str, str]:
    """Return service health status, current UTC time, and version."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "version": APP_VERSION,
    }
