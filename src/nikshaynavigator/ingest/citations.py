"""Validate source and page traceability before producing citations."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Citation:
    document_id: str
    title: str
    year: int
    page_no: int
    headings: tuple[str, ...]
    source_url: str

    def render(self) -> str:
        """Return a human-readable source citation."""
        result = f"{self.title} ({self.year}), p. {self.page_no}"

        if self.headings:
            result += f" — {' > '.join(self.headings)}"

        return result


@dataclass(frozen=True)
class CitationIssue:
    code: str
    detail: str
    document_id: str | None
    page_no: int | None


@dataclass(frozen=True)
class CitationAudit:
    pages_checked: int
    valid_pages: int
    issues: tuple[CitationIssue, ...]

    @property
    def invalid_pages(self) -> int:
        return self.pages_checked - self.valid_pages

    @property
    def coverage_percent(self) -> float:
        if not self.pages_checked:
            return 0.0

        return round(100 * self.valid_pages / self.pages_checked, 2)


class CitationValidationError(ValueError):
    """Raised when a page cannot produce a trustworthy citation."""

    def __init__(self, issues: list[str]) -> None:
        self.issues = tuple(issues)
        super().__init__("; ".join(issues))


def _resolve_year(document: object) -> int | None:
    """Resolve the publication year from explicit document metadata."""

    published_on = getattr(document, "published_on", None)

    if isinstance(published_on, (date, datetime)):
        return published_on.year

    if isinstance(published_on, str):
        match = re.search(r"\b(?:19|20)\d{2}\b", published_on)
        if match:
            return int(match.group())

    metadata = getattr(document, "metadata_", None) or {}

    for key in ("year", "published_year", "publication_year"):
        value = metadata.get(key)

        if isinstance(value, int) and 1900 <= value <= 2100:
            return value

        if isinstance(value, str) and re.fullmatch(r"(?:19|20)\d{2}", value):
            return int(value)

    title = str(getattr(document, "title", "") or "")
    years = re.findall(r"\b(?:19|20)\d{2}\b", title)

    if years:
        return int(years[-1])

    return None


def build_citation(document: object, page: object) -> Citation:
    """Build a citation only when its source information is verifiable."""

    issues: list[str] = []

    document_pk = getattr(document, "id", None)
    page_document_id = getattr(page, "document_id", None)

    title = str(getattr(document, "title", "") or "").strip()
    source_url = str(getattr(document, "source_url", "") or "").strip()
    page_no = getattr(page, "page_no", 0)
    page_text = str(getattr(page, "text", "") or "")
    headings = getattr(page, "headings", [])

    if document_pk != page_document_id:
        issues.append("Page does not belong to the supplied document.")

    if not title:
        issues.append("Document title is missing.")

    year = _resolve_year(document)

    if year is None:
        issues.append("Publication year is missing.")

    parsed_url = urlsplit(source_url)

    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        issues.append("A valid source URL is missing.")

    if not isinstance(page_no, int) or page_no < 1:
        issues.append("Page number must be a positive integer.")

    if not page_text.strip():
        issues.append("Page has no extractable text and cannot be cited.")

    if not isinstance(headings, list) or any(
        not isinstance(item, str) for item in headings
    ):
        issues.append("Heading path must be a list of strings.")

    if issues:
        raise CitationValidationError(issues)

    return Citation(
        document_id=str(getattr(document, "external_id", None) or document_pk),
        title=title,
        year=year,
        page_no=page_no,
        headings=tuple(headings),
        source_url=source_url,
    )


def audit_citations(
    documents: Iterable[object],
    pages: Iterable[object],
) -> CitationAudit:
    """Audit every page and report invalid or untraceable citations."""

    documents_by_id = {document.id: document for document in documents}

    checked = 0
    valid = 0
    issues: list[CitationIssue] = []

    for page in pages:
        checked += 1

        document = documents_by_id.get(page.document_id)

        if document is None:
            issues.append(
                CitationIssue(
                    code="missing_document",
                    detail="No source document exists for this page.",
                    document_id=None,
                    page_no=getattr(page, "page_no", None),
                )
            )
            continue

        try:
            build_citation(document, page)
            valid += 1

        except CitationValidationError as exc:
            for detail in exc.issues:
                issues.append(
                    CitationIssue(
                        code="invalid_citation",
                        detail=detail,
                        document_id=str(getattr(document, "external_id", document.id)),
                        page_no=getattr(page, "page_no", None),
                    )
                )

    return CitationAudit(
        pages_checked=checked,
        valid_pages=valid,
        issues=tuple(issues),
    )
