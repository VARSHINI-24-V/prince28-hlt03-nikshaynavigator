"""Compare PyMuPDF and pypdf on the 10 largest downloaded PDFs."""

import json
import time
from pathlib import Path

from nikshaynavigator.ingest.parse import ParseError, parse_file

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW_ROOT = (ROOT / "data" / "raw").resolve()
NOTES = ROOT / "NOTES.md"

START_MARKER = "<!-- D07_PARSER_COMPARISON_START -->"
END_MARKER = "<!-- D07_PARSER_COMPARISON_END -->"


def load_largest_pdfs(limit: int = 10) -> list[dict]:
    """Select the largest downloaded PDFs using manifest byte sizes."""

    records = []

    with MANIFEST.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            record = json.loads(line)

            if record.get("status") != "downloaded":
                continue

            if Path(record.get("path", "")).suffix.lower() != ".pdf":
                continue

            path = (ROOT / record["path"]).resolve()

            try:
                path.relative_to(RAW_ROOT)
            except ValueError as exc:
                raise ValueError(f"Unsafe manifest path on line {line_number}") from exc

            if not path.is_file():
                continue

            records.append(
                {
                    **record,
                    "resolved_path": path,
                    "file_bytes": path.stat().st_size,
                }
            )

    return sorted(
        records,
        key=lambda item: item["file_bytes"],
        reverse=True,
    )[:limit]


def measure_parser(path: Path, parser_name: str) -> dict:
    """Measure extraction time, pages, characters and empty pages."""

    started = time.perf_counter()

    try:
        parsed = parse_file(path, pdf_parser=parser_name)

        elapsed = time.perf_counter() - started

        return {
            "ok": True,
            "seconds": elapsed,
            "pages": len(parsed.pages),
            "chars": sum(len(page.text) for page in parsed.pages),
            "empty_pages": sum(not page.text.strip() for page in parsed.pages),
            "tables": sum(page.tables for page in parsed.pages),
            "error": "",
        }

    except ParseError as exc:
        return {
            "ok": False,
            "seconds": time.perf_counter() - started,
            "pages": 0,
            "chars": 0,
            "empty_pages": 0,
            "tables": 0,
            "error": f"{exc.reason}: {exc.detail}",
        }


def choose_verdict(mupdf: dict, pypdf: dict) -> str:
    """Choose a verdict based on extraction results."""

    if mupdf["ok"] and not pypdf["ok"]:
        return "PyMuPDF preferred"

    if pypdf["ok"] and not mupdf["ok"]:
        return "pypdf preferred"

    if not mupdf["ok"] and not pypdf["ok"]:
        return "Manual/OCR required"

    if mupdf["chars"] > pypdf["chars"] * 1.02:
        return "PyMuPDF: more text"

    if pypdf["chars"] > mupdf["chars"] * 1.02:
        return "pypdf: more text"

    return "Similar text; PyMuPDF adds tables"


def build_report(rows: list[dict]) -> str:
    """Create a Markdown comparison report."""

    lines = [
        START_MARKER,
        "## D07 — Parser comparison",
        "",
        "Selection: 10 largest downloaded PDFs by manifest file size.",
        "Both parsers were tested without OCR for a native-text comparison.",
        "",
        "| File | Size (MB) | PyMuPDF pages/chars | pypdf pages/chars |",
        "|---|---:|---:|---:|",
    ]

    for row in rows:
        mupdf = row["pymupdf"]
        pypdf = row["pypdf"]

        mupdf_value = f"{mupdf['pages']}/{mupdf['chars']}" if mupdf["ok"] else "FAILED"

        pypdf_value = f"{pypdf['pages']}/{pypdf['chars']}" if pypdf["ok"] else "FAILED"

        filename = row["path"].split("/")[-1]

        lines.append(
            f"| {filename} | {row['file_bytes'] / 1_000_000:.2f} "
            f"| {mupdf_value} | {pypdf_value} |"
        )

    lines.extend(
        [
            "",
            "| File | PyMuPDF time (s) | pypdf time (s) | Tables | Verdict |",
            "|---|---:|---:|---:|---|",
        ]
    )

    for row in rows:
        mupdf = row["pymupdf"]
        pypdf = row["pypdf"]

        lines.append(
            f"| {row['path'].split('/')[-1]} "
            f"| {mupdf['seconds']:.2f} "
            f"| {pypdf['seconds']:.2f} "
            f"| {mupdf['tables'] if mupdf['ok'] else 'N/A'} "
            f"| {row['verdict']} |"
        )

    lines.extend(["", "### Parser errors", ""])

    errors_found = False

    for row in rows:
        for name in ("pymupdf", "pypdf"):
            result = row[name]

            if not result["ok"]:
                errors_found = True
                lines.append(f"- **{row['path']} — {name}:** {result['error']}")

    if not errors_found:
        lines.append("No parser errors in the comparison.")

    lines.extend(["", END_MARKER])

    return "\n".join(lines)


def update_notes(report: str) -> None:
    """Replace the previous comparison section or append it."""

    existing = NOTES.read_text(encoding="utf-8") if NOTES.exists() else ""

    start = existing.find(START_MARKER)
    end = existing.find(END_MARKER)

    if start >= 0 and end >= start:
        end += len(END_MARKER)
        existing = existing[:start] + existing[end:]
    else:
        existing = existing.rstrip()

    NOTES.write_text(
        existing.rstrip() + "\n\n" + report + "\n",
        encoding="utf-8",
    )


def main() -> None:
    records = load_largest_pdfs(limit=10)

    if len(records) < 10:
        raise RuntimeError(f"Expected 10 downloaded PDFs, found {len(records)}.")

    rows = []

    for index, record in enumerate(records, start=1):
        path = record["resolved_path"]

        print(f"[{index}/10] Comparing {path.name}")

        mupdf = measure_parser(path, "pymupdf")
        pypdf = measure_parser(path, "pypdf")

        row = {
            "path": record["path"],
            "file_bytes": record["file_bytes"],
            "pymupdf": mupdf,
            "pypdf": pypdf,
            "verdict": choose_verdict(mupdf, pypdf),
        }

        rows.append(row)

        print(f"    PyMuPDF: {mupdf['chars']} chars, {mupdf['seconds']:.2f}s")
        print(f"    pypdf:   {pypdf['chars']} chars, {pypdf['seconds']:.2f}s")
        print(f"    Verdict: {row['verdict']}")

    report = build_report(rows)
    update_notes(report)

    print("\nComparison completed.")
    print(f"Compared: {len(rows)} PDFs")
    print(f"Report written to: {NOTES}")


if __name__ == "__main__":
    main()
