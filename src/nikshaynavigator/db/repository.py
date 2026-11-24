"""All SQL for documents lives here. Endpoints never write SQL themselves."""

import re
from typing import Any

from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from nikshaynavigator.db.models import Document, Page

FILTER_KEY = re.compile(r"^[a-z_][a-z0-9_]{0,40}$")


def to_dict(doc: Document) -> dict[str, Any]:
    """Same flat shape the API returned on Day 2, so clients don't break."""
    return {
        "id": doc.external_id,
        **doc.metadata_,
        "title": doc.title,
        "doc_type": doc.doc_type,
        "source_url": doc.source_url,
        "licence": doc.licence,
        "published_on": doc.published_on.isoformat() if doc.published_on else None,
    }


def _value_candidates(value: str) -> list[Any]:
    """A URL value may represent text, a number, a boolean, or a list item."""
    out: list[Any] = [value, [value]]
    lowered = value.lower()

    if lowered in ("true", "false"):
        out.append(lowered == "true")
    elif re.fullmatch(r"-?\d+", value):
        out.append(int(value))
    elif re.fullmatch(r"-?\d+\.\d+", value):
        out.append(float(value))

    return out


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(
        self,
        *,
        q: str | None,
        filters: dict[str, str],
        limit: int,
        offset: int,
        sort_by: str = "external_id",
        order: str = "asc",
    ) -> tuple[int, list[dict[str, Any]]]:
        stmt = select(Document)

        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                or_(
                    Document.title.ilike(like),
                    cast(Document.metadata_, Text).ilike(like),
                )
            )

        for key, value in filters.items():
            stmt = stmt.where(
                or_(
                    *(
                        Document.metadata_.contains({key: candidate})
                        for candidate in _value_candidates(value)
                    )
                )
            )

        total = await self.session.scalar(
            select(func.count()).select_from(stmt.subquery())
        )

        sort_columns = {
            "external_id": Document.external_id,
            "title": Document.title,
            "published_on": Document.published_on,
        }

        sort_column = sort_columns[sort_by]

        if order == "desc":
            sort_column = sort_column.desc()
        else:
            sort_column = sort_column.asc()

        rows = await self.session.scalars(
            stmt.order_by(sort_column).limit(limit).offset(offset)
        )

        return total or 0, [to_dict(doc) for doc in rows]

    async def get(self, external_id: str) -> dict[str, Any] | None:
        doc = await self.session.scalar(
            select(Document).where(Document.external_id == external_id)
        )
        return to_dict(doc) if doc else None

    async def get_page(
        self,
        external_id: str,
        page_no: int,
    ) -> dict[str, Any] | None:
        """Retrieve one page belonging to a document."""

        stmt = (
            select(Page)
            .join(Document, Page.document_id == Document.id)
            .where(
                Document.external_id == external_id,
                Page.page_no == page_no,
            )
        )

        page = await self.session.scalar(stmt)

        if page is None:
            return None

        return {
            "document_id": external_id,
            "page_no": page.page_no,
            "headings": page.headings or [],
            "text": page.text,
        }
