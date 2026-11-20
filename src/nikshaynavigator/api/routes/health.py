"""Health and readiness endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from nikshaynavigator.api.deps import check_db
from nikshaynavigator.config import get_settings

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health() -> dict:
    """Return application health and deployed version."""
    settings = get_settings()

    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "version": settings.git_sha,
    }


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
