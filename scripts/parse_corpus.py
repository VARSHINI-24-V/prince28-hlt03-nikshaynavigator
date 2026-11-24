"""Parse downloaded corpus files and store pages in PostgreSQL."""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from sqlalchemy import select

from nikshaynavigator.config import get_settings
from nikshaynavigator.db.models import ParseFailure
from nikshaynavigator.db.session import make_engine, make_sessionmaker
from nikshaynavigator.ingest.parse import ParseError, parse_file
from nikshaynavigator.ingest.store import (
    store_parse_failure,
    store_parsed_document,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW_ROOT = (ROOT / "data" / "raw").resolve()


def load_manifest() -> list[dict]:
    """Load successfully downloaded records from the JSONL manifest."""

    records = []

    with MANIFEST.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON in manifest line {line_number}"
                ) from exc

            if record.get("status") != "downloaded":
                continue

            if not record.get("path") or not record.get("sha256"):
                raise ValueError(f"Missing path or sha256 at line {line_number}")

            records.append(record)

    return records


def resolve_document_path(relative_path: str) -> Path:
    """Resolve a manifest path and prevent access outside data/raw."""

    candidate = (ROOT / relative_path).resolve()

    try:
        candidate.relative_to(RAW_ROOT)
    except ValueError as exc:
        raise ParseError(
            "unsafe_path",
            f"Path is outside data/raw: {relative_path}",
        ) from exc

    return candidate


def calculate_sha256(path: Path) -> str:
    """Calculate the SHA-256 checksum of a file."""

    digest = hashlib.sha256()

    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


def make_external_id(record: dict) -> str:
    """Create a stable document ID from its source URL or relative path."""

    identity = record.get("url") or record["path"]

    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


async def get_failed_paths(session_factory) -> set[str]:
    """Return paths already recorded in the failure table."""

    async with session_factory() as session:
        result = await session.scalars(select(ParseFailure.path))
        return set(result.all())


async def process_record(
    record: dict,
    session_factory,
    *,
    ocr_lang: str | None = None,
) -> str:
    """Parse one document and persist either its pages or failure."""

    relative_path = record["path"]
    expected_hash = record["sha256"]
    source_url = record.get("url")
    external_id = make_external_id(record)

    try:
        path = resolve_document_path(relative_path)

        if not path.is_file():
            raise ParseError(
                "missing",
                f"Downloaded file does not exist: {relative_path}",
            )

        actual_hash = calculate_sha256(path)

        if actual_hash.lower() != expected_hash.lower():
            raise ParseError(
                "hash_mismatch",
                "File SHA-256 does not match the manifest.",
            )

        # Extract content using the appropriate parser.
        parsed = parse_file(
            path,
            ocr_lang=ocr_lang,
        )

        # The curated manifest title takes precedence.
        parsed.title = record.get("title") or parsed.title

        async with session_factory() as session, session.begin():
            document = await store_parsed_document(
                session,
                external_id=external_id,
                parsed=parsed,
                path=relative_path,
                sha256=actual_hash,
                source_url=source_url,
                licence=record.get("licence"),
                doc_type=parsed.kind,
            )

        return f"PARSED: {document.title} ({len(parsed.pages)} pages)"

    except ParseError as exc:
        failure_hash = (
            expected_hash
            if len(expected_hash) == 64
            else hashlib.sha256(relative_path.encode()).hexdigest()
        )

        async with session_factory() as session, session.begin():
            await store_parse_failure(
                session,
                path=relative_path,
                sha256=failure_hash,
                source_url=source_url,
                error=exc,
            )

        return f"FAILED: {relative_path} [{exc.reason}]"


async def run(args: argparse.Namespace) -> None:
    """Run the corpus parsing pipeline."""

    records = load_manifest()

    settings = get_settings()
    engine = make_engine(settings)
    session_factory = make_sessionmaker(engine)

    try:
        failed_paths = await get_failed_paths(session_factory)

        if args.retry_failed:
            records = [record for record in records if record["path"] in failed_paths]
        else:
            records = [
                record for record in records if record["path"] not in failed_paths
            ]

        if args.limit is not None:
            records = records[: args.limit]

        print(f"Documents selected: {len(records)}")

        parsed_count = 0
        failed_count = 0

        for index, record in enumerate(records, start=1):
            try:
                result = await process_record(
                    record,
                    session_factory,
                    ocr_lang=args.ocr,
                )
            except Exception as exc:
                print(f"[{index}/{len(records)}] ERROR: {record['path']}: {exc}")
                raise

            print(f"[{index}/{len(records)}] {result}")

            if result.startswith("PARSED:"):
                parsed_count += 1
            else:
                failed_count += 1

        print("\nParsing summary")
        print(f"Parsed: {parsed_count}")
        print(f"Failed: {failed_count}")
        print(f"Total processed: {parsed_count + failed_count}")

    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse NikshayNavigator's downloaded corpus."
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of documents to process.",
    )

    parser.add_argument(
        "--ocr",
        choices=["eng", "tam", "eng+tam"],
        default=None,
        help="OCR pages with insufficient native text using Tesseract.",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Process only files previously recorded as parsing failures.",
    )

    args = parser.parse_args()

    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
