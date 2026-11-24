"""Unit tests for citation traceability validation."""

from datetime import date
from types import SimpleNamespace

import pytest

from nikshaynavigator.ingest.citations import (
    CitationValidationError,
    audit_citations,
    build_citation,
)


def make_document(**overrides):
    """Create a valid document for citation tests."""

    values = {
        "id": 1,
        "external_id": "drtb-2025",
        "title": "National Guidelines for Management of DR-TB 2025",
        "published_on": date(2025, 1, 1),
        "source_url": "https://tbcindia.mohfw.gov.in/guidelines/",
        "metadata_": {},
    }

    values.update(overrides)
    return SimpleNamespace(**values)


def make_page(**overrides):
    """Create a valid page for citation tests."""

    values = {
        "document_id": 1,
        "page_no": 50,
        "text": "Treatment guidelines for drug-resistant tuberculosis.",
        "headings": [
            "RESISTANT TB",
            "3.9 Management of special situations",
            "3.9.1 Pregnancy and lactation",
        ],
    }

    values.update(overrides)
    return SimpleNamespace(**values)


def test_build_valid_citation():
    citation = build_citation(make_document(), make_page())

    assert citation.document_id == "drtb-2025"
    assert citation.year == 2025
    assert citation.page_no == 50
    assert citation.headings[-1] == "3.9.1 Pregnancy and lactation"
    assert "2025" in citation.render()
    assert "p. 50" in citation.render()


def test_rejects_missing_publication_year():
    document = make_document(
        title="National TB Guidelines",
        published_on=None,
    )

    with pytest.raises(CitationValidationError, match="Publication year"):
        build_citation(document, make_page())


def test_rejects_missing_source_url():
    document = make_document(source_url="")

    with pytest.raises(CitationValidationError, match="source URL"):
        build_citation(document, make_page())


def test_rejects_page_belonging_to_another_document():
    page = make_page(document_id=999)

    with pytest.raises(CitationValidationError, match="does not belong"):
        build_citation(make_document(), page)


def test_rejects_invalid_page_number():
    page = make_page(page_no=0)

    with pytest.raises(CitationValidationError, match="positive integer"):
        build_citation(make_document(), page)


def test_rejects_empty_page_text():
    page = make_page(text="   ")

    with pytest.raises(CitationValidationError, match="no extractable text"):
        build_citation(make_document(), page)


def test_audit_reports_valid_and_invalid_pages():
    document = make_document()

    valid_page = make_page()

    invalid_page = make_page(
        page_no=51,
        text="",
    )

    result = audit_citations(
        [document],
        [valid_page, invalid_page],
    )

    assert result.pages_checked == 2
    assert result.valid_pages == 1
    assert result.invalid_pages == 1
    assert result.coverage_percent == 50.0
    assert len(result.issues) == 1


def test_audit_reports_missing_documents():
    page = make_page(document_id=999)

    result = audit_citations([], [page])

    assert result.pages_checked == 1
    assert result.valid_pages == 0
    assert result.invalid_pages == 1
    assert result.issues[0].code == "missing_document"


def test_empty_audit_has_zero_coverage():
    result = audit_citations([], [])

    assert result.pages_checked == 0
    assert result.coverage_percent == 0.0
