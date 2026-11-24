"""Async database storage for parsed NikshayNavigator documents."""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from nikshaynavigator.db.models import (
    Document,
    Page,
    ParseFailure,
)
from nikshaynavigator.ingest.parse import ParsedDoc, ParseError


async def store_parsed_document(
    session: AsyncSession,
    *,
    external_id: str,
    parsed: ParsedDoc,
    path: str,
    sha256: str,
    source_url: str | None = None,
    licence: str | None = None,
    doc_type: str | None = None,
) -> Document:
    """Store a parsed document and replace its existing pages.

    The caller owns the transaction and must commit or roll it back.
    """

    if not external_id.strip():
        raise ValueError("external_id cannot be empty.")

    if not parsed.pages:
        raise ValueError("Cannot store a document with no parsed pages.")

    # Find an existing document using its stable external ID.
    result = await session.execute(
        select(Document).where(Document.external_id == external_id)
    )
    document = result.scalar_one_or_none()

    table_count = sum(page.tables for page in parsed.pages)

    metadata = {
        "parser": parsed.parser,
        "kind": parsed.kind,
        "pages": len(parsed.pages),
        "tables": table_count,
        "source_path": path,
    }

    if document is None:
        document = Document(
            external_id=external_id,
            title=parsed.title,
            source_url=source_url,
            licence=licence,
            doc_type=doc_type or parsed.kind,
            sha256=sha256,
            metadata_=metadata,
        )
        session.add(document)

    else:
        # Refresh document metadata and file information.
        document.title = parsed.title
        document.source_url = source_url
        document.licence = licence
        document.doc_type = doc_type or parsed.kind
        document.sha256 = sha256
        document.metadata_ = {
            **(document.metadata_ or {}),
            **metadata,
        }

    # Generate the document ID before inserting pages.
    await session.flush()

    # Replace previously stored pages to make repeated processing safe.
    await session.execute(delete(Page).where(Page.document_id == document.id))

    new_pages = [
        Page(
            document_id=document.id,
            page_no=page.page_no,
            text=page.text,
            headings=page.headings,
        )
        for page in parsed.pages
    ]

    session.add_all(new_pages)

    # Successful parsing removes any previous failure for this file.
    await session.execute(delete(ParseFailure).where(ParseFailure.path == path))

    await session.flush()

    return document


async def store_parse_failure(
    session: AsyncSession,
    *,
    path: str,
    sha256: str,
    error: ParseError,
    source_url: str | None = None,
) -> ParseFailure:
    """Record a parsing failure or increment its retry count.

    The caller owns the transaction and must commit or roll it back.
    """

    result = await session.execute(
        select(ParseFailure).where(ParseFailure.path == path)
    )

    failure = result.scalar_one_or_none()

    if failure is None:
        failure = ParseFailure(
            path=path,
            sha256=sha256,
            source_url=source_url,
            reason=error.reason,
            detail=error.detail,
            attempts=1,
        )
        session.add(failure)

    else:
        failure.sha256 = sha256
        failure.source_url = source_url
        failure.reason = error.reason
        failure.detail = error.detail
        failure.attempts += 1

    await session.flush()

    return failure
