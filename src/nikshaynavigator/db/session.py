"""Async SQLAlchemy engine and session factory."""

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from nikshaynavigator.config import Settings
from nikshaynavigator.db.url import to_asyncpg_url


def make_engine(settings: Settings):
    return create_async_engine(
        to_asyncpg_url(settings.database_url),
        echo=True,
        pool_size=5,
        max_overflow=2,
        pool_pre_ping=True,
    )


def make_sessionmaker(engine):
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
