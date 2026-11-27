"""One job = one document: fetch, hash, parse, extract and store."""

import asyncio
import hashlib
import logging
import re
import tempfile
import time
from pathlib import Path

import httpx
from arq import Retry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nikshaynavigator.db.models import Document, IngestItem
from nikshaynavigator.ingest.fetch import (
    RETRYABLE,
    HostGate,
    Robots,
    Source,
    fetch_one,
)
from nikshaynavigator.ingest.parse import ParseError, parse_file
from nikshaynavigator.ingest.store import (
    document_id,
    save_document,
    save_failure,
)
from nikshaynavigator.llm.extract import (
    document_text,
    extract,
    save,
)

logger = logging.getLogger("nikshaynavigator.worker")

GITHUB_BLOB = re.compile(r"^https://github\.com/([^/]+/[^/]+)/blob/[^/]+/(.+)$")


class Permanent(Exception):
    """An error that should go directly to the dead-letter list."""


def plan(
    records: list[dict],
    done_ids: set[str],
    *,
    source: str = "",
    limit: int = 0,
) -> list[dict]:
    """Select downloaded documents that have not already been ingested."""

    todo = []
    seen = set(done_ids)

    for record in records:
        if record.get("status") != "downloaded":
            continue

        if source and record.get("source") != source:
            continue

        doc_hash = document_id(record["sha256"])

        if doc_hash in seen:
            continue

        seen.add(doc_hash)
        todo.append(record)

    return todo[:limit] if limit else todo


def raw_url(record: dict) -> str:
    """Convert a GitHub blob URL into a commit-pinned raw URL."""

    match = GITHUB_BLOB.match(record["url"])

    if record.get("via") == "git" and match and record.get("commit"):
        return (
            f"https://raw.githubusercontent.com/"
            f"{match[1]}/{record['commit']}/{match[2]}"
        )

    return record["url"]


def sha256_of(path: Path) -> str:
    """Calculate the SHA-256 hash of a downloaded file."""

    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)

    return digest.hexdigest()


class Pace:
    """Share a rate limit across all concurrent document jobs."""

    def __init__(
        self,
        per_minute: float,
        clock=time.monotonic,
        sleep=asyncio.sleep,
    ) -> None:
        if per_minute <= 0:
            raise ValueError("per_minute must be greater than zero")

        self._gap = 60 / per_minute
        self._clock = clock
        self._sleep = sleep
        self._next = 0.0

    async def wait(self) -> None:
        """Wait until the next model call is permitted."""

        now = self._clock()
        delay = max(0.0, self._next - now)

        self._next = max(now, self._next) + self._gap

        if delay:
            await self._sleep(delay)


async def get_file(
    record: dict,
    folder: Path,
    client: httpx.AsyncClient,
    sleep=asyncio.sleep,
) -> Path:
    """Use a local file when available; otherwise download it."""

    path = Path(record["path"])

    if path.is_file():
        return path

    if record.get("via") == "manual":
        raise Permanent("download: manually supplied file exists only on the laptop")

    source = Source(
        raw_url(record),
        record.get("source") or "unknown",
        record.get("licence") or "unknown",
        record.get("title") or "",
    )

    result = await fetch_one(
        client,
        source,
        root=folder,
        raw_dir=folder / "raw",
        robots=Robots(client),
        gate=HostGate(0.5, sleep),
        slots=asyncio.Semaphore(1),
        max_attempts=2,
        sleep=sleep,
    )

    if result["status"] == "downloaded":
        return folder / result["path"]

    problem = f"download {result['status']}: {result.get('error', '')}"

    if result["status"] == "blocked" or result.get("http_status") not in {
        None,
        *RETRYABLE,
    }:
        raise Permanent(problem)

    raise RuntimeError(problem)


async def process(
    ctx: dict,
    session: AsyncSession,
    item: IngestItem,
) -> tuple[str, int]:
    """Process one item and return its final status and page count."""

    record = dict(item.record)

    with tempfile.TemporaryDirectory() as folder:
        path = await get_file(
            record,
            Path(folder),
            ctx["http"],
        )

        actual_hash = await asyncio.to_thread(
            sha256_of,
            path,
        )

        expected_hash = record.get("sha256")

        if expected_hash and actual_hash.lower() != expected_hash.lower():
            raise Permanent("download: SHA-256 does not match the manifest")

        record["sha256"] = actual_hash

        # Check the SHA column because older records used URL-based IDs.
        document = await session.scalar(
            select(Document).where(Document.sha256 == actual_hash)
        )

        status = "skipped"

        if document is None:
            try:
                async with ctx["parse_lock"]:
                    parsed = await asyncio.to_thread(
                        parse_file,
                        path,
                        ocr_lang=ctx["settings"].ocr_lang,
                    )

            except ParseError as error:
                await save_failure(session, record, error)

                # Preserve the failure record before raising Permanent.
                await session.commit()

                raise Permanent(f"parse: {error.reason}") from error

            document = await save_document(
                session,
                record,
                parsed,
            )

            status = "done"

    pages = int((document.metadata_ or {}).get("pages", 0))

    # Metadata extraction is optional when no prompt/model is configured.
    task = ctx.get("extract")

    note = (document.metadata_ or {}).get("extract") or {}

    if task and (note.get("prompt") != task["version"] or "error" in note):
        await ctx["pace"].wait()

        text = await document_text(
            session,
            document,
            task["chars"],
        )

        result = await extract(
            ctx["gateway"],
            task["schema"],
            task["prompt"],
            task["version"],
            document.title,
            text,
        )

        await save(
            session,
            document,
            result,
            task["version"],
            task["schema"],
        )

        if result.record is None:
            reason = (
                result.errors[-1] if result.errors else "metadata extraction failed"
            )
            raise Permanent(f"extract: {reason[:200]}")

        status = "done"

    return status, pages


async def ingest_document(
    ctx: dict,
    item_id: int,
) -> str:
    """Execute one queued document with persistent retry tracking."""

    max_tries = ctx["settings"].ingest_max_tries

    async with ctx["sessionmaker"]() as session:
        item = await session.get(IngestItem, item_id)

        if item is None or item.status not in ("queued", "running"):
            return "ignored"

        # The attempt counter lives in PostgreSQL, not only in Redis.
        if item.attempts >= max_tries:
            item.status = "failed"
            item.error = f"gave up: started {item.attempts} times and never finished"
            await session.commit()
            return "failed"

        item.status = "running"
        item.attempts += 1
        attempt = item.attempts

        await session.commit()

        try:
            item.status, item.pages = await process(
                ctx,
                session,
                item,
            )
            item.error = ""
        except asyncio.CancelledError:
            await session.rollback()

            item = await session.get(IngestItem, item_id)

            if item is not None and item.status == "running":
                item.status = "queued"
                item.error = "Worker interrupted; awaiting retry"
                await session.commit()

            raise
        except Permanent as error:
            await session.rollback()

            # Reload after rollback before updating the item.
            item = await session.get(IngestItem, item_id)

            if item is not None:
                item.status = "failed"
                item.error = str(error)[:500]

        except Exception as error:
            await session.rollback()

            item = await session.get(IngestItem, item_id)

            if item is None:
                raise

            reason = f"{type(error).__name__}: {error}"[:500]

            if attempt >= max_tries:
                item.status = "failed"
                item.error = f"gave up after {attempt} tries: {reason}"

            else:
                item.status = "queued"
                item.error = f"try {attempt} failed: {reason}"

                await session.commit()

                logger.warning(
                    "Item %s will be retried: %s",
                    item_id,
                    reason,
                )

                # 30 seconds after attempt 1, 60 after attempt 2.
                raise Retry(defer=attempt * 30) from error

        await session.commit()

        logger.info(
            "Item %s finished with status %s",
            item_id,
            item.status,
        )

        return item.status
