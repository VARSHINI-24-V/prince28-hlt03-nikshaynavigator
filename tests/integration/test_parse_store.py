"""Integration tests for parsed-document PostgreSQL storage."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from nikshaynavigator.config import Settings
from nikshaynavigator.db.models import Page, ParseFailure
from nikshaynavigator.db.session import make_engine, make_sessionmaker
from nikshaynavigator.ingest.parse import (
    ParsedDoc,
    ParsedPage,
    ParseError,
)
from nikshaynavigator.ingest.store import (
    store_parse_failure,
    store_parsed_document,
)


@pytest.fixture
async def db_engine(database_url):
    """Create an engine connected to the temporary test database."""

    settings = Settings(
        app_env="ci",
        database_url=database_url,
        _env_file=None,
    )

    engine = make_engine(settings)
    yield engine
    await engine.dispose()


def make_parsed_doc(
    title: str = "TB Treatment Guidelines",
    pages: list[ParsedPage] | None = None,
) -> ParsedDoc:
    """Create a predictable parsed document for testing."""

    return ParsedDoc(
        parser="pymupdf",
        kind="pdf",
        title=title,
        pages=pages
        or [
            ParsedPage(
                page_no=1,
                text="Tuberculosis diagnosis and treatment guidelines.",
                headings=["Tuberculosis", "Diagnosis"],
                tables=0,
            ),
            ParsedPage(
                page_no=2,
                text="Treatment protocols and patient follow-up.",
                headings=["Tuberculosis", "Treatment"],
                tables=1,
            ),
        ],
    )


async def test_store_parsed_document_saves_pages(db_engine):
    """A parsed document and its pages should be persisted."""

    external_id = f"parse-{uuid4().hex}"
    path = f"data/raw/test/{uuid4().hex}.pdf"
    sha256 = uuid4().hex * 2

    async with make_sessionmaker(db_engine)() as session, session.begin():
        document = await store_parsed_document(
            session,
            external_id=external_id,
            parsed=make_parsed_doc(),
            path=path,
            sha256=sha256,
            source_url="https://example.org/guideline.pdf",
            licence="Test licence",
            doc_type="guideline",
        )

        assert document.id is not None
        assert document.title == "TB Treatment Guidelines"
        assert document.metadata_["parser"] == "pymupdf"
        assert document.metadata_["pages"] == 2

        result = await session.scalars(
            select(Page).where(Page.document_id == document.id).order_by(Page.page_no)
        )
        pages = list(result.all())

        assert len(pages) == 2
        assert pages[0].page_no == 1
        assert pages[0].headings == ["Tuberculosis", "Diagnosis"]
        assert "diagnosis" in pages[0].text.lower()

        assert pages[1].page_no == 2
        assert document.metadata_["tables"] == 1


async def test_store_parse_failure_tracks_retries(db_engine):
    """A failed file should be recorded and retry attempts incremented."""

    path = f"data/raw/test/{uuid4().hex}.pdf"
    sha256 = uuid4().hex * 2

    async with make_sessionmaker(db_engine)() as session, session.begin():
        first = await store_parse_failure(
            session,
            path=path,
            sha256=sha256,
            source_url="https://example.org/scanned.pdf",
            error=ParseError(
                "no_text_layer",
                "No usable text was extracted.",
            ),
        )

        first_id = first.id

        assert first.reason == "no_text_layer"
        assert first.attempts == 1

        second = await store_parse_failure(
            session,
            path=path,
            sha256=sha256,
            source_url="https://example.org/scanned.pdf",
            error=ParseError(
                "corrupt",
                "Retry failed because the PDF is damaged.",
            ),
        )

        assert second.id == first_id
        assert second.attempts == 2
        assert second.reason == "corrupt"


async def test_store_parsed_document_is_idempotent(db_engine):
    """Reprocessing a document should replace pages, not duplicate them."""

    external_id = f"retry-{uuid4().hex}"
    path = f"data/raw/test/{uuid4().hex}.pdf"

    first_doc = make_parsed_doc()

    updated_doc = make_parsed_doc(
        title="Updated TB Treatment Guidelines",
        pages=[
            ParsedPage(
                page_no=1,
                text="Updated tuberculosis treatment information.",
                headings=["Tuberculosis", "Updated Treatment"],
                tables=0,
            )
        ],
    )

    async with make_sessionmaker(db_engine)() as session, session.begin():
        first = await store_parsed_document(
            session,
            external_id=external_id,
            parsed=first_doc,
            path=path,
            sha256=uuid4().hex * 2,
        )

        first_id = first.id

        second = await store_parsed_document(
            session,
            external_id=external_id,
            parsed=updated_doc,
            path=path,
            sha256=uuid4().hex * 2,
        )

        assert second.id == first_id
        assert second.title == "Updated TB Treatment Guidelines"

        page_count = await session.scalar(
            select(func.count()).select_from(Page).where(Page.document_id == second.id)
        )

        assert page_count == 1

        page = await session.scalar(select(Page).where(Page.document_id == second.id))

        assert page is not None
        assert "Updated tuberculosis" in page.text
        assert page.headings == ["Tuberculosis", "Updated Treatment"]

        failure_count = await session.scalar(
            select(func.count())
            .select_from(ParseFailure)
            .where(ParseFailure.path == path)
        )

        assert failure_count == 0
