"""Read-only parsing validation for newly downloaded PDFs."""

import asyncio
from pathlib import Path

from nikshaynavigator.config import get_settings
from nikshaynavigator.db.ingest_jobs import IngestRepository
from nikshaynavigator.db.session import make_engine, make_sessionmaker
from nikshaynavigator.ingest.fetch import Manifest
from nikshaynavigator.ingest.parse import ParseError, parse_file


async def main() -> int:
    settings = get_settings()
    engine = make_engine(settings)

    try:
        sessionmaker = make_sessionmaker(engine)
        repository = IngestRepository(sessionmaker)

        # Read existing hashes from Neon. No database modifications.
        known_ids = await repository.known_ids()

        manifest = Manifest(settings.manifest_file)
        records = list(manifest.records.values())

        candidates = [
            record
            for record in records
            if record.get("status") == "downloaded"
            and record.get("sha256") not in known_ids
        ]

        print(f"New PDF candidates: {len(candidates)}")

        passed = 0
        failed = 0

        for index, record in enumerate(candidates, start=1):
            title = record.get("title", "Untitled")
            path = Path(record["path"])

            print(f"\n[{index}/{len(candidates)}] {title}")

            if not path.is_file():
                print("FAILED: Local PDF file is missing.")
                failed += 1
                continue

            try:
                parsed = parse_file(path)

                page_count = len(parsed.pages)
                total_chars = sum(len(page.text) for page in parsed.pages)
                empty_pages = sum(not page.text.strip() for page in parsed.pages)

                print("Result: PASS")
                print(f"Parser: {parsed.parser}")
                print(f"Pages: {page_count}")
                print(f"Extracted characters: {total_chars}")
                print(f"Pages with no extracted text: {empty_pages}")
                print(f"Detected scanned pages: {parsed.scanned_pages}")

                passed += 1

            except ParseError as error:
                print("Result: FAILED")
                print(f"Reason: {error.reason}")
                print(f"Details: {error.detail}")
                failed += 1

        print("\n=== PDF VALIDATION SUMMARY ===")
        print(f"Candidates: {len(candidates)}")
        print(f"Parsed successfully: {passed}")
        print(f"Failed: {failed}")

        return 1 if failed else 0

    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
