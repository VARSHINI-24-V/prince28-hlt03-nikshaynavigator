import os
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from nikshaynavigator.db.models import Base, Document
from nikshaynavigator.db.url import to_asyncpg_url

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not configured",
)


@pytest.fixture
async def db_session():
    engine = create_async_engine(
        to_asyncpg_url(TEST_DATABASE_URL),
        pool_pre_ping=True,
    )
    session_factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
    )

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        async with session_factory() as session:
            yield session
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()


def make_document():
    unique_id = f"integration-{uuid.uuid4().hex}"

    return Document(
        external_id=unique_id,
        title="Integration test document",
        doc_type="record",
        sha256=uuid.uuid4().hex * 2,
        metadata_={"topic": "integration-test"},
    )


async def test_database_insert_and_retrieve(db_session):
    document = make_document()
    db_session.add(document)
    await db_session.commit()

    result = await db_session.scalar(
        select(Document).where(Document.external_id == document.external_id)
    )

    assert result is not None
    assert result.title == "Integration test document"


async def test_database_jsonb_metadata_filter(db_session):
    document = make_document()
    db_session.add(document)
    await db_session.commit()

    result = await db_session.scalars(
        select(Document).where(
            Document.metadata_.contains({"topic": "integration-test"})
        )
    )

    assert any(item.external_id == document.external_id for item in result)


async def test_database_rejects_duplicate_external_id(db_session):
    document = make_document()
    db_session.add(document)
    await db_session.commit()

    duplicate = Document(
        external_id=document.external_id,
        title="Duplicate document",
        doc_type="record",
        sha256="b" * 64,
        metadata_={},
    )
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.commit()

    await db_session.rollback()
