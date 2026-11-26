from hashlib import sha256
from uuid import uuid4

import pytest
from sqlalchemy import select

from nikshaynavigator.config import Settings
from nikshaynavigator.db.models import Document, Page
from nikshaynavigator.db.session import make_engine, make_sessionmaker
from nikshaynavigator.llm.doc_meta import DocMeta
from nikshaynavigator.llm.extract import Extraction, pending, save


@pytest.fixture
async def db_engine(database_url):
    settings = Settings(
        app_env="ci",
        database_url=database_url,
        _env_file=None,
    )

    engine = make_engine(settings)

    try:
        yield engine
    finally:
        await engine.dispose()


def make_document(title, metadata=None):
    external_id = uuid4().hex

    return Document(
        external_id=external_id,
        title=title,
        source_url="https://example.org/guideline.pdf",
        licence="Test licence",
        doc_type="pdf",
        sha256=sha256(external_id.encode()).hexdigest(),
        metadata_=metadata or {},
    )


VALID_RECORD = {
    "doc_kind": "guideline",
    "year": 2025,
    "language": "en",
    "summary": "Official guidance for tuberculosis programme implementation.",
    "topics": ["drug-resistant TB", "treatment"],
    "document": ["DR-TB Management Guidelines"],
    "topic": ["drug-resistant TB"],
    "population": ["Adults"],
    "recommendation": ["Follow the recommended treatment workflow"],
    "supersedes": [],
}


async def test_extraction_metadata_merges_without_losing_parser_fields(db_engine):
    session_factory = make_sessionmaker(db_engine)
    document = make_document(
        "DR-TB Guidelines",
        metadata={
            "parser": "pymupdf_ocr",
            "pages": 40,
            "tables": 3,
            "scanned_pages": [1, 3],
            "source_path": "data/raw/example.pdf",
        },
    )

    async with session_factory() as session:
        session.add(document)
        await session.flush()

        session.add(
            Page(
                document_id=document.id,
                page_no=1,
                text="Tuberculosis guideline content.",
                headings=["Tuberculosis"],
            )
        )
        await session.commit()

        result = Extraction(
            record=DocMeta.model_validate(VALID_RECORD),
            attempts=2,
            errors=["First response had an invalid year."],
            model="fake-model",
            tokens_in=200,
            tokens_out=50,
            cost_inr=0.002,
        )

        await save(session, document, result, "extract_v1", DocMeta)

        stored = await session.scalar(
            select(Document).where(Document.id == document.id)
        )

        assert stored is not None
        assert stored.metadata_["parser"] == "pymupdf_ocr"
        assert stored.metadata_["pages"] == 40
        assert stored.metadata_["tables"] == 3
        assert stored.metadata_["scanned_pages"] == [1, 3]
        assert stored.metadata_["doc_kind"] == "guideline"
        assert stored.metadata_["year"] == 2025
        assert stored.metadata_["extract"]["prompt"] == "extract_v1"
        assert stored.metadata_["extract"]["attempts"] == 2
        assert stored.metadata_["extract"]["repaired"] is True


async def test_failed_extraction_preserves_parser_and_removes_stale_metadata(
    db_engine,
):
    session_factory = make_sessionmaker(db_engine)

    document = make_document(
        "Older guideline",
        metadata={
            "parser": "pymupdf",
            "pages": 58,
            "source_path": "data/raw/older.pdf",
            "doc_kind": "guideline",
            "year": 2025,
            "topics": ["old topics"],
            "summary": "Old metadata from an earlier extraction attempt.",
        },
    )

    async with session_factory() as session:
        session.add(document)
        await session.commit()

        result = Extraction(
            record=None,
            attempts=3,
            errors=["summary: invalid length"],
            model="fake-model",
        )

        await save(session, document, result, "extract_v2", DocMeta)

        stored = await session.scalar(
            select(Document).where(Document.id == document.id)
        )

        assert stored is not None
        assert stored.metadata_["parser"] == "pymupdf"
        assert stored.metadata_["pages"] == 58
        assert stored.metadata_["source_path"] == "data/raw/older.pdf"
        assert "doc_kind" not in stored.metadata_
        assert "year" not in stored.metadata_
        assert "topics" not in stored.metadata_
        assert stored.metadata_["extract"]["prompt"] == "extract_v2"
        assert stored.metadata_["extract"]["error"] == "summary: invalid length"


async def test_pending_respects_prompt_version_and_retry_failed(db_engine):
    session_factory = make_sessionmaker(db_engine)

    not_extracted = make_document(
        "Not extracted",
        metadata={"parser": "pymupdf", "pages": 10},
    )

    completed_v1 = make_document(
        "Completed v1",
        metadata={
            "parser": "pymupdf",
            "pages": 20,
            "extract": {
                "prompt": "extract_v1",
                "model": "fake-model",
                "attempts": 1,
            },
        },
    )

    completed_v2 = make_document(
        "Completed v2",
        metadata={
            "parser": "pymupdf",
            "pages": 30,
            "extract": {
                "prompt": "extract_v2",
                "model": "fake-model",
                "attempts": 1,
            },
        },
    )

    failed_v1 = make_document(
        "Failed v1",
        metadata={
            "parser": "pymupdf",
            "pages": 40,
            "extract": {
                "prompt": "extract_v1",
                "model": "fake-model",
                "attempts": 3,
                "error": "summary: invalid length",
            },
        },
    )

    async with session_factory() as session:
        session.add_all(
            [
                not_extracted,
                completed_v1,
                completed_v2,
                failed_v1,
            ]
        )
        await session.commit()

        tracked_ids = {
            not_extracted.external_id,
            completed_v1.external_id,
            completed_v2.external_id,
            failed_v1.external_id,
        }

        normal = await pending(session, "extract_v1")
        normal_ids = {item.external_id for item in normal} & tracked_ids

        assert normal_ids == {
            not_extracted.external_id,
            completed_v2.external_id,
        }

        retry = await pending(
            session,
            "extract_v1",
            retry_failed=True,
        )
        retry_ids = {item.external_id for item in retry} & tracked_ids

        assert retry_ids == {
            not_extracted.external_id,
            completed_v2.external_id,
            failed_v1.external_id,
        }

        assert completed_v1.external_id not in retry_ids
