"""FastAPI dependencies for database sessions and repositories."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from nikshaynavigator.db.repository import DocumentRepository


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
