"""Health and readiness endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, Response

from nikshaynavigator.api.deps import check_db
from nikshaynavigator.config import get_settings

router = APIRouter(tags=["Health"])


def _health_payload() -> dict[str, str]:
    """Build the health response using application settings."""
    settings = get_settings()

    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "version": settings.git_sha,
    }


@router.get("/health")
async def health() -> dict[str, str]:
    """Return application health and deployed version."""
    return _health_payload()


@router.head("/health", include_in_schema=False)
async def health_head() -> Response:
    """Support HEAD requests from uptime monitoring services."""
    response = JSONResponse(content=_health_payload())

    return Response(
        status_code=response.status_code,
        headers=dict(response.headers),
    )


@router.get("/ready")
async def ready(database: bool = Depends(check_db)) -> dict:
    """Check whether the application and database are ready."""
    if not database:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "checks": {"database": False},
            },
        )

    return {
        "status": "ready",
        "checks": {"database": True},
    }
