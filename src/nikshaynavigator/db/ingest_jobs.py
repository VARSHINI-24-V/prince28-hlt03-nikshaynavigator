"""Database repository for ingestion jobs and items."""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from nikshaynavigator.db.models import (
    Document,
    IngestItem,
    IngestJob,
)


class IngestRepository:
    """Keep all ingestion-job SQL operations in one place."""

    def __init__(self, sessionmaker: async_sessionmaker):
        self.sessionmaker = sessionmaker

    async def known_ids(self) -> set[str]:
        """Return content hashes of documents already in the database."""

        async with self.sessionmaker() as session:
            result = await session.scalars(
                select(Document.sha256).where(Document.doc_type != "record")
            )
            return set(result.all())

    async def create(self, records: list[dict]) -> tuple[str, list[int]]:
        """Create one job and its document items in a single transaction."""

        if not records:
            raise ValueError("Cannot create an empty ingestion job.")

        job_id = uuid4().hex

        async with self.sessionmaker() as session, session.begin():
            job = IngestJob(
                id=job_id,
                requested=len(records),
            )
            session.add(job)

            items = [
                IngestItem(
                    job_id=job_id,
                    record=record,
                    status="queued",
                )
                for record in records
            ]

            session.add_all(items)
            await session.flush()

            item_ids = [item.id for item in items]

        return job_id, item_ids

    async def failed_records(self) -> list[dict]:
        """Return records belonging to permanently failed items."""

        async with self.sessionmaker() as session:
            result = await session.scalars(
                select(IngestItem)
                .where(IngestItem.status == "failed")
                .order_by(IngestItem.updated_at.desc())
            )

            return [dict(item.record) for item in result.all()]

    async def dead_letter(self, limit: int = 50) -> list[dict]:
        """Return failed items without a successfully ingested document."""

        async with self.sessionmaker() as session:
            has_successful_document = (
                select(Document.id)
                .where(
                    Document.sha256 == IngestItem.record["sha256"].astext,
                    Document.doc_type != "record",
                )
                .exists()
            )

            result = await session.scalars(
                select(IngestItem)
                .where(
                    IngestItem.status == "failed",
                    ~has_successful_document,
                )
                .order_by(IngestItem.updated_at.desc())
                .limit(limit)
            )

            return [
                {
                    "item_id": item.id,
                    "job_id": item.job_id,
                    "title": item.record.get("title", ""),
                    "source": item.record.get("source", ""),
                    "url": item.record.get("url", ""),
                    "status": item.status,
                    "attempts": item.attempts,
                    "error": item.error,
                    "updated_at": (
                        item.updated_at.isoformat() if item.updated_at else None
                    ),
                }
                for item in result.all()
            ]

    async def progress(self, job_id: str) -> dict | None:
        """Return the progress and status counts for one ingestion job."""

        async with self.sessionmaker() as session:
            job = await session.get(IngestJob, job_id)

            if job is None:
                return None

            result = await session.scalars(
                select(IngestItem)
                .where(IngestItem.job_id == job_id)
                .order_by(IngestItem.id)
            )

            items = list(result.all())

            counts = {
                "queued": 0,
                "running": 0,
                "done": 0,
                "skipped": 0,
                "failed": 0,
            }

            for item in items:
                if item.status in counts:
                    counts[item.status] += 1

            pages = sum(item.pages for item in items)

            finished = counts["queued"] == 0 and counts["running"] == 0

            return {
                "job_id": job.id,
                "requested": job.requested,
                **counts,
                "pages": pages,
                "finished": finished,
            }
