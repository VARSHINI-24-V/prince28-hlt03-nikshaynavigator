"""Health and readiness endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from nikshaynavigator.api.deps import check_db

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health() -> dict:
    """Check whether the API process is running."""
    return {"status": "healthy"}


@router.get("/ready")
async def ready(database: bool = Depends(check_db)) -> dict:
    """Check whether the API and its database are ready."""
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
