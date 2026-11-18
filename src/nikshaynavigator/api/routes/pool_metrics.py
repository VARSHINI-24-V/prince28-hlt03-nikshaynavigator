"""Database connection pool monitoring endpoint."""

from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["Monitoring"])


@router.get("/metrics/db-pool")
async def database_pool_metrics(request: Request) -> dict[str, Any]:
    """Return SQLAlchemy connection pool statistics."""

    engine = getattr(request.app.state, "engine", None)

    if engine is None:
        raise HTTPException(
            status_code=503,
            detail="Database engine is unavailable",
        )

    pool = engine.pool

    pool_size = pool.size()
    checked_out = pool.checkedout()
    checked_in = pool.checkedin()
    overflow = pool.overflow()

    return {
        "pool_size": pool_size,
        "max_overflow": 2,
        "max_connections": pool_size + 2,
        "checked_out": checked_out,
        "checked_in": checked_in,
        "overflow": overflow,
        "status": "available",
    }
