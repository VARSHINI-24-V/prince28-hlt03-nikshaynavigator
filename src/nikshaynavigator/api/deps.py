"""FastAPI dependencies for database sessions and repositories."""

import secrets
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from nikshaynavigator.config import get_settings
from nikshaynavigator.db.feedback import AnswerFeedbackRepository
from nikshaynavigator.db.ingest_jobs import IngestRepository
from nikshaynavigator.db.llm_calls import LlmCallRepository
from nikshaynavigator.db.repository import DocumentRepository
from nikshaynavigator.ingest.fetch import Manifest
from nikshaynavigator.llm.gateway import LLMGateway
from nikshaynavigator.workers.queue import (
    IngestQueue,
    close_queue,
    connect_queue,
    ping_queue,
)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Provide one database session per request."""
    session_factory = request.app.state.session_factory

    async with session_factory() as session:
        yield session


async def get_repo(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DocumentRepository:
    """Provide a document repository."""
    return DocumentRepository(session)


async def check_db(request: Request) -> bool:
    """Check whether PostgreSQL is reachable."""
    engine = request.app.state.engine

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False


async def get_gateway(request: Request) -> LLMGateway:
    """Provide the application LLM gateway."""
    return request.app.state.gateway


async def get_usage_repo(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> LlmCallRepository:
    """Provide the LLM usage repository."""
    return LlmCallRepository(session)


async def get_feedback_repo(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AnswerFeedbackRepository:
    """Provide the answer feedback repository."""
    return AnswerFeedbackRepository(session)


GatewayDep = Annotated[LLMGateway, Depends(get_gateway)]

UsageDep = Annotated[LlmCallRepository, Depends(get_usage_repo)]

FeedbackDep = Annotated[
    AnswerFeedbackRepository,
    Depends(get_feedback_repo),
]


async def get_ingest_repo(request: Request) -> IngestRepository:
    """Provide the ingestion repository."""

    return IngestRepository(request.app.state.session_factory)


async def get_manifest() -> list[dict]:
    """Load the current ingestion manifest."""

    settings = get_settings()
    manifest = Manifest(settings.manifest_file)

    return list(manifest.records.values())


async def get_queue():
    """Provide a checked Redis queue connection."""

    redis = None

    try:
        redis = await connect_queue()
        await ping_queue(redis)

    except (RedisError, OSError, TimeoutError) as error:
        if redis is not None:
            await close_queue(redis)

        raise HTTPException(
            status_code=503,
            detail="Ingestion queue is unavailable.",
        ) from error

    try:
        yield IngestQueue(redis)

    finally:
        await close_queue(redis)


async def require_admin(
    x_admin_token: Annotated[
        str | None,
        Header(alias="X-Admin-Token"),
    ] = None,
) -> None:
    """Protect ingestion requests using the configured admin token."""

    expected = get_settings().admin_token

    if not expected:
        raise HTTPException(
            status_code=403,
            detail="Set ADMIN_TOKEN to allow ingestion here.",
        )

    if not x_admin_token or not secrets.compare_digest(
        x_admin_token,
        expected,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing admin token.",
        )


IngestRepoDep = Annotated[
    IngestRepository,
    Depends(get_ingest_repo),
]

ManifestDep = Annotated[
    list[dict],
    Depends(get_manifest),
]

QueueDep = Annotated[
    IngestQueue,
    Depends(get_queue),
]
