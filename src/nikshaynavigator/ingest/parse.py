"""Document parsing utilities for NikshayNavigator."""

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
import trafilatura
from pypdf import PdfReader

# Supported document types
TEXT_TYPES = {".txt", ".md", ".markdown", ".rst", ".adoc"}
DATA_TYPES = {".json", ".csv", ".xml"}

# Maximum characters per text-based page
PAGE_CHARS = 3000

# Minimum useful text expected on a PDF page
MIN_CHARS_PER_PAGE = 50


# ==============================
# PARSED OUTPUT STRUCTURES
# ==============================


@dataclass
class ParsedPage:
    """Represents one extracted document page."""

    page_no: int
    text: str
    headings: list[str] = field(default_factory=list)
    tables: int = 0


@dataclass
class ParsedDoc:
    """Represents a completely parsed document."""

    parser: str
    kind: str
    title: str
    pages: list[ParsedPage]
    scanned_pages: list[int] = field(default_factory=list)


class ParseError(Exception):
    """Raised when a document cannot be parsed."""

    def __init__(self, reason: str, detail: str):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}")


# ==============================
# TEXT CLEANING
# ==============================


def clean_text(text: str) -> str:
    """Normalize extracted text and remove unwanted characters."""

    # Unicode normalization
    text = unicodedata.normalize("NFKC", text)

    # Remove null characters and soft hyphens
    text = text.replace("\x00", "")
    text = text.replace("\u00ad", "")

    # Join words split across lines by PDF hyphenation
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)

    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Remove excessive spaces
    text = re.sub(r"[ \t]+", " ", text)

    # Remove excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# ==============================
# HEADER / FOOTER REMOVAL
# ==============================


def drop_repeated_lines(pages: list[str]) -> list[str]:
    """Remove repeated headers, footers and page numbers."""

    if len(pages) < 3:
        return pages

    edge_lines = Counter()
    page_edges = []

    for page in pages:
        lines = page.splitlines()

        non_empty_indices = [index for index, line in enumerate(lines) if line.strip()]

        edge_indices = set(non_empty_indices[:2] + non_empty_indices[-2:])

        page_edges.append(edge_indices)

        for index in edge_indices:
            edge_lines[lines[index].strip()] += 1

    threshold = max(2, int(len(pages) * 0.20))

    repeated = {line for line, count in edge_lines.items() if count >= threshold}

    page_number_pattern = re.compile(
        r"^(?:page\s*)?\d+(?:\s*(?:of|/)\s*\d+)?$",
        re.IGNORECASE,
    )

    cleaned_pages = []

    for page, edge_indices in zip(pages, page_edges):
        lines = page.splitlines()
        cleaned_lines = []

        for index, line in enumerate(lines):
            stripped = line.strip()

            is_repeated = index in edge_indices and stripped in repeated

            is_page_number = index in edge_indices and bool(
                page_number_pattern.fullmatch(stripped)
            )

            if is_repeated or is_page_number:
                continue

            cleaned_lines.append(line)

        cleaned_pages.append("\n".join(cleaned_lines))

    return cleaned_pages


def heading_title(title: str) -> str:
    """Remove Markdown anchor syntax from a heading title."""

    title = title.strip()

    # Remove trailing Markdown heading markers.
    title = re.sub(r"\s+#+\s*$", "", title)

    # Remove explicit anchors such as {#section-name}.
    title = re.sub(r"\s*\{#[^}]+\}\s*$", "", title)

    # Remove HTML anchor tags.
    title = re.sub(r"</?a\b[^>]*>", "", title, flags=re.IGNORECASE)

    # Remove anchor links such as [¶](#section-name).
    title = re.sub(r"\s*\[[^\]]*\]\(#[^)]+\)", "", title)

    return title.strip()


def parse_markdown_headings(text: str) -> list[tuple[int, str]]:
    """Extract Markdown headings while ignoring fenced code blocks."""

    headings = []
    inside_code = False
    fence_marker = ""

    for line in text.splitlines():
        stripped = line.lstrip()

        # Detect fenced code blocks using ``` or ~~~.
        fence = re.match(r"^(`{3,}|~{3,})", stripped)

        if fence:
            marker = fence.group(1)

            if not inside_code:
                inside_code = True
                fence_marker = marker[0]
            elif marker[0] == fence_marker:
                inside_code = False

            continue

        if inside_code:
            continue

        # Match Markdown headings: # to ######.
        match = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)

        if not match:
            continue

        level = len(match.group(1))
        title = heading_title(match.group(2))

        if title:
            headings.append((level, title))

    return headings


def with_heading_paths(pages: list[ParsedPage]) -> list[ParsedPage]:
    """Attach the active heading hierarchy to every page."""

    heading_stack: list[tuple[int, str]] = []

    for page in pages:
        page_headings = parse_markdown_headings(page.text)

        for level, title in page_headings:
            # Avoid adding the same active heading twice.
            if heading_stack and heading_stack[-1] == (level, title):
                continue

            # Remove headings at the same or deeper level.
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()

            heading_stack.append((level, title))

        # Save the complete active hierarchy after processing the page.
        page.headings = [title for _, title in heading_stack]

    return pages


def _body_size(doc: pymupdf.Document) -> float:
    """Find the most common text font size, weighted by character count."""

    sizes = Counter()

    # Inspect the first 30 pages to estimate normal body-text size.
    for page_number in range(min(30, doc.page_count)):
        page = doc.load_page(page_number)
        blocks = page.get_text("dict").get("blocks", [])

        for block in blocks:
            if block.get("type") != 0:
                continue

            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    size = round(float(span.get("size", 0)), 1)

                    if text and size > 0:
                        sizes[size] += len(text)

    if not sizes:
        return 10.0

    return float(sizes.most_common(1)[0][0])


def _page_heading_candidates(
    page: pymupdf.Page,
    body_size: float,
) -> list[tuple[int, str]]:
    """Identify likely headings using font size and bold formatting."""

    candidates = []
    blocks = page.get_text("dict").get("blocks", [])

    for block in blocks:
        if block.get("type") != 0:
            continue

        for line in block.get("lines", []):
            spans = line.get("spans", [])

            heading = clean_text("".join(span.get("text", "") for span in spans))

            if not heading or len(heading) > 120:
                continue

            size = max(
                (float(span.get("size", 0)) for span in spans),
                default=0,
            )

            bold = any(int(span.get("flags", 0)) & 16 for span in spans)

            is_heading = size >= body_size * 1.20 or (bold and size >= body_size * 1.05)

            if not is_heading:
                continue

            if size >= body_size * 1.60:
                level = 1
            elif size >= body_size * 1.30:
                level = 2
            else:
                level = 3

            candidates.append((level, heading))

    return candidates


def parse_pdf_pymupdf(
    path: Path,
    *,
    ocr_lang: str | None = None,
    ocr_dpi: int = 300,
) -> ParsedDoc:
    """Extract PDF text, using Tesseract OCR on pages with little native text."""

    try:
        with pymupdf.open(path) as doc:
            if doc.needs_pass:
                raise ParseError("encrypted", "PDF requires a password.")

            if doc.page_count == 0:
                raise ParseError("empty", "PDF contains no pages.")

            body_size = _body_size(doc)
            pdf_pages = list(doc)

            original_texts = []
            ocr_pages: set[int] = set()

            # 1. Extract native text; OCR only pages with insufficient text.
            for page_no, page in enumerate(pdf_pages, start=1):
                native_text = clean_text(page.get_text("text", sort=True))

                page_text = native_text

                if ocr_lang and len(native_text) < MIN_CHARS_PER_PAGE:
                    try:
                        text_page = page.get_textpage_ocr(
                            language=ocr_lang,
                            dpi=ocr_dpi,
                            full=True,
                        )

                        page_text = clean_text(
                            page.get_text(
                                "text",
                                textpage=text_page,
                                sort=True,
                            )
                        )

                        if page_text:
                            ocr_pages.add(page_no)

                    except Exception as exc:
                        raise ParseError(
                            "ocr_failed",
                            f"OCR failed on page {page_no}: {exc}",
                        ) from exc

                original_texts.append(page_text)

            # 2. Remove repeated headers and footers.
            cleaned_texts = drop_repeated_lines(original_texts)

            removed_lines: set[str] = set()

            for original, cleaned in zip(original_texts, cleaned_texts):
                original_lines = {
                    line.strip().casefold()
                    for line in original.splitlines()
                    if line.strip()
                }

                cleaned_lines = {
                    line.strip().casefold()
                    for line in cleaned.splitlines()
                    if line.strip()
                }

                removed_lines.update(original_lines - cleaned_lines)

            # 3. Identify heading candidates on native-text pages.
            all_candidates = [
                []
                if page_no in ocr_pages
                else _page_heading_candidates(page, body_size)
                for page_no, page in enumerate(pdf_pages, start=1)
            ]

            heading_frequency = Counter(
                clean_text(heading).casefold()
                for candidates in all_candidates
                for _, heading in candidates
            )

            repeat_threshold = max(3, int(doc.page_count * 0.02))

            repeated_heading_labels = {
                heading
                for heading, count in heading_frequency.items()
                if count >= repeat_threshold
            }

            heading_stack: list[tuple[int, str]] = []
            parsed_pages: list[ParsedPage] = []

            # 4. Build the page objects.
            for page_no, (page, page_text, candidates) in enumerate(
                zip(pdf_pages, cleaned_texts, all_candidates),
                start=1,
            ):
                for level, heading in candidates:
                    heading_key = clean_text(heading).casefold()

                    if (
                        page_no == 1
                        and heading == heading.upper()
                        and len(heading.split()) >= 4
                        and not re.match(r"^\d+(?:\.\d+)*\b", heading)
                    ):
                        continue

                    if heading_key in removed_lines:
                        continue

                    if heading_key in repeated_heading_labels:
                        continue

                    if re.fullmatch(r"\d+", heading_key):
                        continue

                    if re.match(
                        r"^(?:fig(?:ure)?|table)\.?\s*\d",
                        heading_key,
                    ):
                        continue

                    if heading_key.startswith("foot notes to "):
                        continue

                    if heading_stack and heading_stack[-1] == (
                        level,
                        heading,
                    ):
                        continue

                    while heading_stack and heading_stack[-1][0] >= level:
                        heading_stack.pop()

                    heading_stack.append((level, heading))

                heading_path = [heading for _, heading in heading_stack]

                # OCR output does not preserve original font information,
                # so OCR pages do not create new font-based headings.

                markdown_tables = []

                if len(page.get_drawings()) >= 4:
                    table_finder = page.find_tables()

                    for table in table_finder.tables:
                        markdown = table.to_markdown()

                        if markdown.strip():
                            markdown_tables.append(markdown)

                table_text = "\n\n".join(markdown_tables)
                final_text = clean_text(page_text + "\n\n" + table_text)

                parsed_pages.append(
                    ParsedPage(
                        page_no=page_no,
                        text=final_text,
                        headings=heading_path,
                        tables=len(markdown_tables),
                    )
                )

            # 5. Check whether the document has enough extractable text.
            total_chars = sum(len(page.text) for page in parsed_pages)

            if total_chars < MIN_CHARS_PER_PAGE:
                reason = "no_text_layer" if not ocr_lang else "ocr_failed"

                raise ParseError(
                    reason,
                    f"Only {total_chars} characters extracted.",
                )
                # Detect image-based pages with insufficient native text.

            scanned_pages = [
                page_no
                for page_no, pdf_page in enumerate(pdf_pages, start=1)
                if pdf_page.get_images(full=True)
                and (
                    len(parsed_pages[page_no - 1].text.strip()) < MIN_CHARS_PER_PAGE
                    or page_no in ocr_pages
                )
            ]

            metadata = doc.metadata or {}

            return ParsedDoc(
                parser="pymupdf_ocr" if ocr_pages else "pymupdf",
                kind="pdf",
                title=metadata.get("title") or path.stem,
                pages=parsed_pages,
                scanned_pages=scanned_pages,
            )

    except ParseError:
        raise

    except (pymupdf.FileDataError, RuntimeError, ValueError) as exc:
        raise ParseError("corrupt", str(exc)) from exc


def parse_pdf_pypdf(path: Path) -> ParsedDoc:
    """Extract PDF page text using pypdf as an alternative parser."""

    try:
        reader = PdfReader(str(path), strict=False)

        # Check whether the PDF requires a password.
        if reader.is_encrypted:
            raise ParseError(
                "encrypted",
                "PDF requires a password.",
            )

        if len(reader.pages) == 0:
            raise ParseError(
                "empty",
                "PDF contains no pages.",
            )

        raw_pages = []

        # Extract text page by page.
        for page_no, page in enumerate(reader.pages, start=1):
            try:
                page_text = clean_text(page.extract_text() or "")
            except Exception as exc:
                raise ParseError(
                    "corrupt",
                    f"Could not extract page {page_no}: {exc}",
                ) from exc

            raw_pages.append(page_text)

        # Remove repeated headers and footers.
        cleaned_pages = drop_repeated_lines(raw_pages)

        parsed_pages = [
            ParsedPage(
                page_no=page_no,
                text=page_text,
                headings=[],
                tables=0,
            )
            for page_no, page_text in enumerate(cleaned_pages, start=1)
        ]

        total_chars = sum(len(page.text) for page in parsed_pages)

        # Detect scanned PDFs without a usable text layer.
        if total_chars < MIN_CHARS_PER_PAGE:
            raise ParseError(
                "no_text_layer",
                f"Only {total_chars} characters extracted using pypdf.",
            )

        metadata = reader.metadata
        title = (
            str(metadata.title).strip() if metadata and metadata.title else path.stem
        )

        return ParsedDoc(
            parser="pypdf",
            kind="pdf",
            title=title,
            pages=parsed_pages,
        )

    except ParseError:
        raise

    except Exception as exc:
        raise ParseError("corrupt", str(exc)) from exc


def _split_text_into_pages(text: str) -> list[str]:
    """Split long extracted text into chunks without breaking paragraphs unnecessarily."""

    remaining = text.strip()
    chunks = []

    while remaining:
        if len(remaining) <= PAGE_CHARS:
            chunks.append(remaining)
            break

        cut = remaining.rfind("\n\n", 0, PAGE_CHARS)

        if cut < PAGE_CHARS // 2:
            cut = remaining.rfind("\n", 0, PAGE_CHARS)

        if cut < PAGE_CHARS // 2:
            cut = PAGE_CHARS

        chunks.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()

    return [chunk for chunk in chunks if chunk]


def parse_html(path: Path) -> ParsedDoc:
    """Extract clean HTML content, headings and tables using Trafilatura."""

    try:
        raw_html = path.read_text(
            encoding="utf-8",
            errors="replace",
        )

        if not raw_html.strip():
            raise ParseError("empty", "HTML file is empty.")

        # Extract clean content in Markdown format.
        markdown = trafilatura.extract(
            raw_html,
            output_format="markdown",
            include_tables=True,
            include_comments=False,
            favor_precision=True,
        )

        if not markdown or len(markdown.strip()) < MIN_CHARS_PER_PAGE:
            raise ParseError(
                "empty",
                "Trafilatura could not extract sufficient HTML content.",
            )

        # Extract document metadata separately.
        metadata = trafilatura.bare_extraction(
            raw_html,
            include_tables=True,
            include_comments=False,
            with_metadata=True,
        )

        title = (
            getattr(metadata, "title", None) if metadata is not None else None
        ) or path.stem

        # Clean and split the extracted Markdown.
        markdown = clean_text(markdown)
        chunks = _split_text_into_pages(markdown)

        parsed_pages = [
            ParsedPage(
                page_no=page_no,
                text=chunk,
                headings=[],
                tables=chunk.count("\n|---"),
            )
            for page_no, chunk in enumerate(chunks, start=1)
        ]

        # Carry heading paths through the generated pages.
        parsed_pages = with_heading_paths(parsed_pages)

        return ParsedDoc(
            parser="trafilatura",
            kind="html",
            title=title,
            pages=parsed_pages,
        )

    except ParseError:
        raise

    except (OSError, ValueError, RuntimeError) as exc:
        raise ParseError("corrupt", str(exc)) from exc


def parse_text_file(path: Path) -> ParsedDoc:
    """Parse plain-text, Markdown and structured data files."""

    try:
        raw_text = path.read_text(
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise ParseError("corrupt", str(exc)) from exc

    text = clean_text(raw_text)

    if not text:
        raise ParseError(
            "empty",
            "File contains no usable text.",
        )

    # Split long text into logical pages.
    chunks = _split_text_into_pages(text)

    parsed_pages = [
        ParsedPage(
            page_no=page_no,
            text=chunk,
            headings=[],
            tables=chunk.count("\n|---"),
        )
        for page_no, chunk in enumerate(chunks, start=1)
    ]

    # Extract Markdown heading hierarchy.
    parsed_pages = with_heading_paths(parsed_pages)

    suffix = path.suffix.lower()

    return ParsedDoc(
        parser="plain_text",
        kind="data" if suffix in DATA_TYPES else "text",
        title=path.stem,
        pages=parsed_pages,
    )


def parse_file(
    path: str | Path,
    pdf_parser: str = "pymupdf",
    *,
    ocr_lang: str | None = None,
) -> ParsedDoc:
    """Select the appropriate parser based on the file extension."""

    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        if pdf_parser == "pymupdf":
            return parse_pdf_pymupdf(
                path,
                ocr_lang=ocr_lang,
            )

        if pdf_parser == "pypdf":
            if ocr_lang:
                raise ParseError(
                    "unsupported_type",
                    "OCR is supported only with PyMuPDF.",
                )

            return parse_pdf_pypdf(path)

        raise ParseError(
            "unsupported_type",
            f"Unknown PDF parser: {pdf_parser}",
        )

    if suffix in {".html", ".htm"}:
        return parse_html(path)

    if suffix in TEXT_TYPES | DATA_TYPES:
        return parse_text_file(path)

    raise ParseError(
        "unsupported_type",
        f"Unsupported file extension: {suffix}",
    )
