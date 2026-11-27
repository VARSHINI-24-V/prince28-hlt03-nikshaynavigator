"""Read-only preflight inspection for document ingestion."""

import asyncio
from collections import Counter
from pathlib import Path

from sqlalchemy import func, select

from nikshaynavigator.config import get_settings
from nikshaynavigator.db.ingest_jobs import IngestRepository
from nikshaynavigator.db.models import Document, IngestItem, IngestJob
from nikshaynavigator.db.session import make_engine, make_sessionmaker
from nikshaynavigator.ingest.fetch import Manifest
from nikshaynavigator.workers.ingest import plan


async def main() -> None:
    settings = get_settings()
    manifest_path = Path(settings.manifest_file)

    print("=== MANIFEST ===")
    print(f"Path: {manifest_path}")
    print(f"File exists: {manifest_path.is_file()}")

    manifest = Manifest(settings.manifest_file)
    records = list(manifest.records.values())

    print(f"Manifest records: {len(records)}")
    print(
        "Manifest statuses:",
        dict(Counter(str(r.get("status", "unknown")) for r in records)),
    )

    engine = make_engine(settings)

    try:
        sessionmaker = make_sessionmaker(engine)
        repository = IngestRepository(sessionmaker)
        known_ids = await repository.known_ids()
        print("\n=== MANIFEST HASH MATCHING ===")

        for index, record in enumerate(records, start=1):
            sha = record.get("sha256", "")
            already_stored = sha in known_ids

            print(
                f"{index}. {record.get('title', 'Untitled')} | "
                f"SHA: {sha[:12]} | "
                f"Already stored: {already_stored} | "
                f"URL: {record.get('url', '')}"
            )

        async with sessionmaker() as session:
            document_count = await session.scalar(
                select(func.count()).select_from(Document)
            )
            job_count = await session.scalar(
                select(func.count()).select_from(IngestJob)
            )
            item_statuses = list(
                (await session.scalars(select(IngestItem.status))).all()
            )

        print("\n=== DATABASE (READ ONLY) ===")
        print(f"Documents already stored: {document_count or 0}")
        print(f"Known document SHA-256 hashes: {len(known_ids)}")
        print(f"Existing ingestion jobs: {job_count or 0}")
        print(
            "Existing ingestion item statuses:",
            dict(Counter(item_statuses)),
        )

        candidates = plan(records, known_ids, limit=5)

        print("\n=== FIVE NEW CANDIDATES ===")
        print(f"Eligible candidates: {len(candidates)}")

        for index, record in enumerate(candidates, start=1):
            path_value = record.get("path", "")
            local_exists = bool(path_value) and Path(path_value).is_file()

            print(f"\n{index}. {record.get('title', 'Untitled')}")
            print(f"   Source: {record.get('source', 'unknown')}")
            print(f"   Status: {record.get('status', 'unknown')}")
            print(f"   SHA-256: {record.get('sha256', 'missing')}")
            print(f"   Local file exists: {local_exists}")
            print(f"   Acquisition method: {record.get('via', 'unknown')}")

        if not candidates:
            print("\nNo new candidates found. Do not submit an ingestion request yet.")

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
