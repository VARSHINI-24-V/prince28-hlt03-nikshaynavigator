from unittest.mock import AsyncMock

import pytest

from nikshaynavigator.db.models import Document
from nikshaynavigator.db.repository import DocumentRepository, to_dict


def make_document():
    return Document(
        id=1,
        external_id="drtb-2025-diagnosis",
        title="DR-TB diagnosis guidelines",
        source_url="https://example.com/guideline.pdf",
        licence=None,
        doc_type="record",
        published_on=None,
        sha256="a" * 64,
        metadata_={
            "topic": "Drug-resistant TB diagnosis",
            "year": 2025,
        },
    )


def test_to_dict():
    document = make_document()

    result = to_dict(document)

    assert result["id"] == "drtb-2025-diagnosis"
    assert result["title"] == "DR-TB diagnosis guidelines"
    assert result["topic"] == "Drug-resistant TB diagnosis"
    assert result["year"] == 2025


@pytest.mark.asyncio
async def test_repository_list():
    document = make_document()

    session = AsyncMock()
    session.scalar = AsyncMock(return_value=1)
    session.scalars = AsyncMock(return_value=[document])

    repository = DocumentRepository(session)

    total, items = await repository.list(
        q=None,
        filters={},
        limit=20,
        offset=0,
    )

    assert total == 1
    assert len(items) == 1
    assert items[0]["id"] == "drtb-2025-diagnosis"


@pytest.mark.asyncio
async def test_repository_get_existing():
    document = make_document()

    session = AsyncMock()
    session.scalar = AsyncMock(return_value=document)

    repository = DocumentRepository(session)

    result = await repository.get("drtb-2025-diagnosis")

    assert result is not None
    assert result["id"] == "drtb-2025-diagnosis"


@pytest.mark.asyncio
async def test_repository_get_missing():
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=None)

    repository = DocumentRepository(session)

    result = await repository.get("unknown-document")

    assert result is None
