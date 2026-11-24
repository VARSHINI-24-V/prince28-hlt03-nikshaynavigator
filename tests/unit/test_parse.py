"""Unit tests for NikshayNavigator document parsing."""

from pathlib import Path

import pymupdf
import pytest

from nikshaynavigator.ingest.parse import (
    PAGE_CHARS,
    ParsedPage,
    ParseError,
    _split_text_into_pages,
    clean_text,
    drop_repeated_lines,
    heading_title,
    parse_file,
    parse_html,
    parse_markdown_headings,
    parse_pdf_pymupdf,
    parse_pdf_pypdf,
    parse_text_file,
    with_heading_paths,
)


def test_clean_text_normalizes_unicode():
    result = clean_text("ＴＢ Ｇｕｉｄｅ")
    assert result == "TB Guide"


def test_clean_text_removes_unwanted_characters():
    result = clean_text("Tuber\u00adculosis\x00")
    assert result == "Tuberculosis"


def test_clean_text_joins_hyphenated_words():
    result = clean_text("tuber-\nculosis")
    assert result == "tuberculosis"


def test_drop_repeated_headers_and_footers():
    pages = [
        "NTEP Guidelines\nChapter One\nContent A\nMore A\nPage 1",
        "NTEP Guidelines\nChapter Two\nContent B\nMore B\nPage 2",
        "NTEP Guidelines\nChapter Three\nContent C\nMore C\nPage 3",
    ]

    result = drop_repeated_lines(pages)

    assert "NTEP Guidelines" not in result[0]
    assert "Page 1" not in result[0]
    assert "Content A" in result[0]


def test_heading_title_removes_anchor():
    result = heading_title("Diagnosis {#diagnosis}")
    assert result == "Diagnosis"


def test_parse_markdown_headings_ignores_code_blocks():
    text = """# Tuberculosis

## Diagnosis

```python
# This is code, not a heading
```

### Molecular Testing
"""

    result = parse_markdown_headings(text)

    assert result == [
        (1, "Tuberculosis"),
        (2, "Diagnosis"),
        (3, "Molecular Testing"),
    ]


def test_split_text_into_logical_pages():
    text = "A" * (PAGE_CHARS * 2 + 100)

    result = _split_text_into_pages(text)

    assert len(result) == 3
    assert all(len(page) <= PAGE_CHARS for page in result)
    assert "".join(result) == text


def test_heading_paths_continue_across_pages():
    pages = [
        ParsedPage(1, "# Tuberculosis\n## Diagnosis"),
        ParsedPage(2, "### Molecular Testing\nClinical details"),
        ParsedPage(3, "Additional clinical details"),
    ]

    result = with_heading_paths(pages)

    assert result[0].headings == ["Tuberculosis", "Diagnosis"]
    assert result[1].headings == [
        "Tuberculosis",
        "Diagnosis",
        "Molecular Testing",
    ]
    assert result[2].headings == [
        "Tuberculosis",
        "Diagnosis",
        "Molecular Testing",
    ]


def test_parse_text_file_extracts_markdown(tmp_path):
    path = tmp_path / "guideline.md"

    path.write_text(
        "# TB Guidelines\n\n"
        "## Diagnosis\n\n"
        + ("Tuberculosis diagnosis requires clinical assessment. " * 5),
        encoding="utf-8",
    )

    result = parse_text_file(path)

    assert result.kind == "text"
    assert result.parser == "plain_text"
    assert result.pages[0].headings == ["TB Guidelines", "Diagnosis"]


def test_parse_html_extracts_article(tmp_path):
    path = tmp_path / "guideline.html"

    content = (
        "Tuberculosis treatment requires careful clinical assessment "
        "and regular monitoring of every patient. "
    ) * 5

    path.write_text(
        "<html><head><title>TB Guidelines</title></head>"
        f"<body><article><h1>Tuberculosis</h1><p>{content}</p>"
        "</article></body></html>",
        encoding="utf-8",
    )

    result = parse_html(path)

    assert result.kind == "html"
    assert result.parser == "trafilatura"
    assert "Tuberculosis" in result.pages[0].text


def create_test_pdf(path: Path):
    """Create a small PDF containing extractable text."""

    doc = pymupdf.open()
    page = doc.new_page()

    page.insert_text(
        (72, 72),
        "Tuberculosis treatment guidelines describe diagnosis, "
        "patient assessment, medication, monitoring and follow-up.",
    )

    doc.save(path)
    doc.close()


def test_parse_pdf_pymupdf_extracts_page(tmp_path):
    path = tmp_path / "guideline.pdf"
    create_test_pdf(path)

    result = parse_pdf_pymupdf(path)

    assert result.parser == "pymupdf"
    assert result.kind == "pdf"
    assert result.pages[0].page_no == 1
    assert "Tuberculosis" in result.pages[0].text


def test_parse_pdf_pypdf_extracts_page(tmp_path):
    path = tmp_path / "guideline.pdf"
    create_test_pdf(path)

    result = parse_pdf_pypdf(path)

    assert result.parser == "pypdf"
    assert result.kind == "pdf"
    assert result.pages[0].page_no == 1
    assert "Tuberculosis" in result.pages[0].text


def test_parse_file_dispatches_text_file(tmp_path):
    path = tmp_path / "sample.txt"

    path.write_text(
        "Tuberculosis guidelines contain important clinical information.",
        encoding="utf-8",
    )

    result = parse_file(path)

    assert result.parser == "plain_text"
    assert result.title == "sample"


def test_parse_file_rejects_unknown_pdf_parser(tmp_path):
    path = tmp_path / "sample.pdf"

    with pytest.raises(ParseError, match="Unknown PDF parser"):
        parse_file(path, pdf_parser="unknown")


def test_parse_file_rejects_unsupported_extension(tmp_path):
    path = tmp_path / "sample.xyz"

    with pytest.raises(ParseError, match="Unsupported file extension"):
        parse_file(path)


def test_parse_text_file_rejects_empty_file(tmp_path):
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")

    with pytest.raises(ParseError, match="empty"):
        parse_text_file(path)
