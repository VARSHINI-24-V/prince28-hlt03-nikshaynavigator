"""Measure the downloaded NikshayNavigator corpus and generate capacity reports.

Example:
    uv run python scripts/dataset_report.py --full-pages 5000

Estimates use extracted characters / 4 as a transparent token approximation.
They are planning estimates, not exact tokenizer counts.
"""

import argparse
import json
import math
import re
from collections import defaultdict
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data" / "manifest.jsonl"
DATASET = ROOT / "DATASET.md"
CAPACITY = ROOT / "docs" / "CAPACITY.md"

START = "<!-- generated:start -->"
END = "<!-- generated:end -->"


class VisibleTextParser(HTMLParser):
    """Extract visible HTML text without script and style contents."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def read_manifest() -> list[dict]:
    """Read the latest manifest record for each URL."""
    if not MANIFEST.is_file():
        raise FileNotFoundError(
            f"Manifest not found: {MANIFEST}. Run the downloader first."
        )

    latest: dict[str, dict] = {}

    for line_number, line in enumerate(
        MANIFEST.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue

        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            print(f"Warning: ignoring invalid manifest line {line_number}.")
            continue

        if not isinstance(record, dict) or not record.get("url"):
            print(f"Warning: ignoring incomplete manifest line {line_number}.")
            continue

        latest[record["url"]] = record

    return list(latest.values())


def extract_document(path: Path) -> dict:
    """Return page count and extractable character count for a document."""
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        reader = PdfReader(str(path), strict=False)
        page_count = len(reader.pages)
        text_chars = 0
        empty_pages = 0

        for page in reader.pages:
            page_text = page.extract_text() or ""
            text_chars += len(page_text.strip())
            if len(page_text.strip()) < 50:
                empty_pages += 1

        average_chars = text_chars / page_count if page_count else 0

        return {
            "pages": page_count,
            "text_chars": text_chars,
            "scanned": bool(page_count and average_chars < 50),
            "empty_pages": empty_pages,
            "type": "PDF",
        }

    if suffix in {".html", ".htm"}:
        parser = VisibleTextParser()
        parser.feed(path.read_text(encoding="utf-8", errors="replace"))
        return {
            "pages": None,
            "text_chars": len(" ".join(parser.parts)),
            "scanned": False,
            "empty_pages": 0,
            "type": "HTML",
        }

    if suffix in {".txt", ".md", ".mdx", ".rst", ".adoc", ".csv", ".xml", ".json"}:
        content = path.read_text(encoding="utf-8", errors="replace")
        return {
            "pages": None,
            "text_chars": len(content),
            "scanned": False,
            "empty_pages": 0,
            "type": "Text",
        }

    return {
        "pages": None,
        "text_chars": 0,
        "scanned": False,
        "empty_pages": 0,
        "type": suffix.lstrip(".").upper() or "Unknown",
    }


def markdown_cell(value: object) -> str:
    """Make values safe for Markdown table cells."""
    return str(value or "Not recorded").replace("|", "\\|").replace("\n", " ")


def update_generated(path: Path, header: str, generated: str, footer: str) -> None:
    """Replace only generated content, preserving manually written sections."""
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        content = path.read_text(encoding="utf-8")
    else:
        content = f"{header}\n\n{START}\n{END}\n\n{footer}\n"

    if START not in content or END not in content:
        raise ValueError(
            f"{path.name} must contain generated:start and generated:end markers."
        )

    start_index = content.index(START) + len(START)
    end_index = content.index(END)

    if end_index < start_index:
        raise ValueError(f"Generated markers are in the wrong order in {path.name}.")

    content = (
        content[:start_index]
        + "\n\n"
        + generated.strip()
        + "\n\n"
        + content[end_index:]
    )

    path.write_text(content, encoding="utf-8")


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("Value must be greater than zero.")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure the local corpus and generate DATASET.md and CAPACITY.md."
    )

    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--full-pages", type=positive_int)
    target.add_argument("--full-files", type=positive_int)

    parser.add_argument(
        "--embed-usd",
        type=float,
        default=0.20,
        help="Embedding price in USD per million tokens (default: 0.20).",
    )
    parser.add_argument("--dims", type=positive_int, default=1024)
    parser.add_argument("--chunk-tokens", type=positive_int, default=500)
    parser.add_argument("--usd-inr", type=float, default=95.0)

    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.embed_usd < 0 or args.usd_inr <= 0:
        raise ValueError(
            "Embedding price cannot be negative; USD-INR must be positive."
        )

    records = read_manifest()
    documents: list[dict] = []
    missing: list[str] = []
    errors: list[str] = []
    totals = defaultdict(int)
    source_totals: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for record in records:
        if record.get("status") != "downloaded":
            continue

        relative_path = Path(record.get("path", ""))
        path = (ROOT / relative_path).resolve()

        if not path.is_relative_to(ROOT.resolve()):
            errors.append(f"Unsafe manifest path: {relative_path}")
            continue

        if not path.is_file():
            missing.append(str(relative_path))
            continue

        try:
            measured = extract_document(path)
        except (OSError, ValueError, PdfReadError) as error:
            errors.append(f"{relative_path}: {type(error).__name__}: {error}")
            continue

        size = path.stat().st_size
        source = str(record.get("source") or "unknown")
        title = str(record.get("title") or path.name)
        year_match = re.search(r"\b(?:19|20)\d{2}\b", title)
        year = year_match.group(0) if year_match else "Not recorded"

        document = {
            "title": title,
            "year": year,
            "source": source,
            "path": relative_path.as_posix(),
            "url": record.get("source_url") or record.get("url", ""),
            "licence": record.get("licence", "Not recorded"),
            "sha256": record.get("sha256", ""),
            "bytes": size,
            **measured,
        }
        documents.append(document)

        totals["files"] += 1
        totals["bytes"] += size
        totals["text_chars"] += measured["text_chars"]
        totals["pages"] += measured["pages"] or 0
        totals["pdf_files"] += measured["type"] == "PDF"
        totals["scanned"] += measured["scanned"]

        source_totals[source]["files"] += 1
        source_totals[source]["bytes"] += size
        source_totals[source]["pages"] += measured["pages"] or 0

    if not documents:
        raise ValueError("No readable downloaded documents were found.")

    total_pages = totals["pages"]
    total_chars = totals["text_chars"]
    measured_tokens = math.ceil(total_chars / 4)
    tokens_per_page = measured_tokens / total_pages if total_pages else 0
    chars_per_page = total_chars / total_pages if total_pages else 0

    if args.full_pages:
        full_pages = args.full_pages
        full_tokens = math.ceil(tokens_per_page * full_pages)
        target_description = f"{full_pages:,} pages"
    else:
        full_pages = 0
        full_tokens = math.ceil(measured_tokens / len(documents) * args.full_files)
        target_description = f"{args.full_files:,} files (page count not supplied)"

    chunks = math.ceil(full_tokens / args.chunk_tokens) if full_tokens else 0
    vector_bytes = chunks * args.dims * 4
    vector_mb = vector_bytes / (1024**2)
    estimated_text_bytes = math.ceil(
        (chars_per_page * full_pages) if full_pages else total_chars
    )
    text_mb = estimated_text_bytes / (1024**2)
    embedding_usd = full_tokens / 1_000_000 * args.embed_usd
    embedding_inr = embedding_usd * args.usd_inr

    total_mb = totals["bytes"] / (1024**2)
    scanned_files = [doc for doc in documents if doc["scanned"]]

    dataset_lines = [
        "## Generated collection snapshot",
        "",
        f"- **Generated:** {datetime.now(UTC).date().isoformat()}",
        f"- **Downloaded files measured:** {totals['files']}",
        f"- **PDF files:** {totals['pdf_files']}",
        f"- **Measured PDF pages:** {total_pages:,}",
        f"- **Raw corpus size:** {total_mb:,.2f} MB",
        f"- **Extractable text:** {total_chars:,} characters (~{measured_tokens:,} tokens)",
        f"- **Missing files:** {len(missing)}",
        f"- **Measurement errors:** {len(errors)}",
        f"- **PDFs flagged as possibly scanned:** {len(scanned_files)}",
        "",
        "### Document inventory",
        "",
        "| Document | Year | Source | Pages | MB | Licence / terms recorded | SHA-256 | Source URL |",
        "|---|---:|---|---:|---:|---|---|---|",
    ]

    for doc in sorted(documents, key=lambda item: item["title"].lower()):
        pages = doc["pages"] if doc["pages"] is not None else "n/a"
        url = doc["url"]
        dataset_lines.append(
            "| "
            + " | ".join(
                markdown_cell(value)
                for value in (
                    doc["title"],
                    doc["year"],
                    doc["source"],
                    pages,
                    f"{doc['bytes'] / (1024**2):.2f}",
                    doc["licence"],
                    doc["sha256"][:12] or "Not recorded",
                    f"[source]({url})" if url else "Not recorded",
                )
            )
            + " |"
        )

    dataset_lines.extend(
        [
            "",
            "### Collection by publisher",
            "",
            "| Source | Files | Pages | MB |",
            "|---|---:|---:|---:|",
        ]
    )

    for source, values in sorted(source_totals.items()):
        dataset_lines.append(
            f"| {markdown_cell(source)} | {values['files']} | "
            f"{values['pages']} | {values['bytes'] / (1024**2):.2f} |"
        )

    if scanned_files:
        dataset_lines.extend(["", "### PDFs needing OCR review", ""])
        for doc in scanned_files:
            dataset_lines.append(
                f"- {doc['title']}: {doc['empty_pages']} of "
                f"{doc['pages']} pages contain very little extractable text."
            )

    if missing:
        dataset_lines.extend(["", "### Missing files", ""])
        dataset_lines.extend(f"- `{item}`" for item in missing)

    if errors:
        dataset_lines.extend(["", "### Measurement errors", ""])
        dataset_lines.extend(f"- {item}" for item in errors)

    capacity_lines = [
        "## Generated capacity measurements",
        "",
        f"- **Full corpus target:** {target_description}",
        f"- **Measured files:** {totals['files']:,}",
        f"- **Measured PDF pages:** {total_pages:,}",
        f"- **Measured extractable text:** {total_chars:,} characters",
        f"- **Measured token estimate:** ~{measured_tokens:,} tokens",
        f"- **Measured tokens per PDF page:** ~{tokens_per_page:,.1f}",
        f"- **Chunk size assumption:** {args.chunk_tokens:,} tokens",
        f"- **Embedding dimensions:** {args.dims:,}",
        f"- **Projected full-corpus tokens:** ~{full_tokens:,}",
        f"- **Projected chunks:** ~{chunks:,}",
        f"- **Estimated embedding cost:** USD ${embedding_usd:,.4f}",
        f"- **Estimated embedding cost in INR:** Rs {embedding_inr:,.2f}",
        f"- **Projected float32 vector storage:** ~{vector_mb:,.2f} MB",
        f"- **Approximate extracted-text storage:** ~{text_mb:,.2f} MB",
        f"- **Measured raw-file storage today:** {total_mb:,.2f} MB",
        "",
        "### Assumptions and limitations",
        "",
        "- Token estimates use extracted characters divided by four; no model tokenizer was run.",
        "- Embedding cost assumes the supplied price per million tokens and excludes retries, storage, indexing and application costs.",
        "- Vector storage assumes four bytes per dimension and excludes PostgreSQL indexes and row overhead.",
        "- Extracted-text storage is approximate and excludes metadata and database overhead.",
        "- Scanned PDFs may need OCR; their extracted-text and token estimates may be too low.",
        "- Compare the projected text and vector storage with the actual free-space limit shown in your PostgreSQL provider dashboard.",
    ]

    dataset_header = """# Dataset: NikshayNavigator

Answers TB programme questions for field staff using attributed NTEP guidance.

- **Start target:** 15 core documents (approximately 1,500 pages).
- **Full target:** All applicable guidelines, modules and circulars (5,000+ pages).
- **Collected by:** `scripts/fetch.py` using `examate-student-bot`.
- **Raw downloaded files:** Stored locally under `data/raw/` and excluded from Git."""

    dataset_footer = """## Known gaps

- Initial collection contains 15 documents and 1,382 measured PDF pages.
- The collection is approximately 118 pages below the 1,500-page target.
- Some collected documents are FAQs, training modules and operational guidance,
  rather than standalone national clinical guidelines.
- Additional core NTEP guidelines and circulars still need to be identified.
- Scanned PDFs and documents with extraction errors require further review.
- Third-party copyright and redistribution permissions need verification.
"""

    capacity_header = """# Capacity plan: NikshayNavigator

Full corpus target: All applicable guidelines, modules and circulars (5,000+ pages)."""

    capacity_footer = """## What I conclude

1. Is embedding cost a problem for this product? Answer with the estimated amount above.
2. Do the vectors and extracted text fit in my free PostgreSQL storage? Compare with the actual provider dashboard limit.
3. Which estimate am I least sure about, and how will I measure it better?
4. What changes if the corpus grows ten times? Include storage and embedding estimates."""

    update_generated(DATASET, dataset_header, "\n".join(dataset_lines), dataset_footer)
    update_generated(
        CAPACITY, capacity_header, "\n".join(capacity_lines), capacity_footer
    )

    print(
        f"files={totals['files']} pages={total_pages} "
        f"raw_mb={total_mb:.2f} tokens_estimate={measured_tokens}"
    )
    print("wrote DATASET.md and docs/CAPACITY.md")
    print(f"full_target_tokens_estimate={full_tokens}")
    print(f"projected_chunks={chunks}")
    print(f"estimated_embedding_cost_inr=Rs {embedding_inr:.2f}")
    print(f"projected_vectors_mb={vector_mb:.2f}")

    return 1 if missing or errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
