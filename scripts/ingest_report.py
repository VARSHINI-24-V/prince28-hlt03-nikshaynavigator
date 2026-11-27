"""Generate a database-backed ingestion report without overwriting manual notes."""

import argparse
import asyncio
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

from nikshaynavigator.config import get_settings
from nikshaynavigator.db.models import Document, IngestItem, IngestJob, Page
from nikshaynavigator.db.session import make_engine, make_sessionmaker

START = "<!-- INGEST_REPORT_GENERATED_START -->"
END = "<!-- INGEST_REPORT_GENERATED_END -->"

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "docs" / "INGEST_REPORT.md"


def safe_cell(value: object) -> str:
    """Keep values safe for Markdown table cells."""
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def timestamp(value: datetime | None) -> str:
    if value is None:
        return "Not recorded"
    return value.isoformat()


async def collect_data(job_id: str | None = None) -> dict:
    settings = get_settings()
    engine = make_engine(settings)

    try:
        sessionmaker = make_sessionmaker(engine)

        async with sessionmaker() as session:
            document_count = await session.scalar(
                select(func.count())
                .select_from(Document)
                .where(Document.doc_type != "record")
            )

            distinct_external_ids = await session.scalar(
                select(func.count(func.distinct(Document.external_id))).where(
                    Document.doc_type != "record"
                )
            )

            page_row_count = await session.scalar(
                select(func.count()).select_from(Page)
            )

            text_character_count = await session.scalar(
                select(func.coalesce(func.sum(func.length(Page.text)), 0))
                .join(Document, Page.document_id == Document.id)
                .where(Document.doc_type != "record")
            )

            jobs = list(
                (
                    await session.scalars(
                        select(IngestJob).order_by(IngestJob.created_at)
                    )
                ).all()
            )

            items = list(
                (
                    await session.scalars(select(IngestItem).order_by(IngestItem.id))
                ).all()
            )

        if job_id:
            jobs = [job for job in jobs if job.id == job_id]
            if not jobs:
                raise ValueError(f"Ingestion job not found: {job_id}")

            allowed_ids = {job.id for job in jobs}
            items = [item for item in items if item.job_id in allowed_ids]

        return {
            "document_count": document_count or 0,
            "distinct_external_ids": distinct_external_ids or 0,
            "page_row_count": page_row_count or 0,
            "text_character_count": text_character_count or 0,
            "jobs": jobs,
            "items": items,
        }

    finally:
        await engine.dispose()


def render_generated_section(data: dict) -> str:
    jobs = data["jobs"]
    items = data["items"]

    counts = Counter(item.status for item in items)

    total_pages = sum(item.pages or 0 for item in items)
    text_characters = data["text_character_count"]
    estimated_tokens = round(text_characters / 4)
    tokens_per_page = (
        estimated_tokens / data["page_row_count"] if data["page_row_count"] else 0
    )
    retried = [item for item in items if (item.attempts or 0) > 1]

    terminal_items = counts["done"] + counts["skipped"] + counts["failed"]

    requested = sum(job.requested for job in jobs)

    is_finished = (
        terminal_items == requested and counts["queued"] == 0 and counts["running"] == 0
    )

    generated_at = datetime.now(UTC).isoformat()

    lines = [
        "## Database-generated ingestion results",
        "",
        f"- **Generated at (UTC):** {generated_at}",
        f"- **Jobs included:** {len(jobs)}",
        f"- **Requested items:** {requested}",
        f"- **Done:** {counts['done']}",
        f"- **Skipped:** {counts['skipped']}",
        f"- **Failed:** {counts['failed']}",
        f"- **Queued:** {counts['queued']}",
        f"- **Running:** {counts['running']}",
        f"- **Pages recorded by ingestion items:** {total_pages}",
        f"- **Extracted text characters:** {text_characters:,}",
        f"- **Estimated tokens (characters / 4):** {estimated_tokens:,}",
        f"- **Estimated tokens per PDF page:** {tokens_per_page:.1f}",
        f"- **Items retried:** {len(retried)}",
        f"- **All selected jobs finished:** {'Yes' if is_finished else 'No'}",
        "",
        "### Database document verification",
        "",
        (
            f"- Distinct ingested documents (`doc_type != record`): "
            f"{data['document_count']}"
        ),
        f"- Distinct external IDs: {data['distinct_external_ids']}",
        f"- Stored page rows in database: {data['page_row_count']}",
        (
            f"- Duplicate external IDs: "
            f"{data['document_count'] - data['distinct_external_ids']}"
        ),
        "",
        "### Individual ingestion jobs",
        "",
        "| Job ID | Created at | Requested | Done | Skipped | Failed | Queued | Running | Pages | Retries |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    items_by_job = defaultdict(list)
    for item in items:
        items_by_job[item.job_id].append(item)

    for job in jobs:
        job_items = items_by_job[job.id]
        job_counts = Counter(item.status for item in job_items)

        job_pages = sum(item.pages or 0 for item in job_items)
        job_retries = sum(1 for item in job_items if (item.attempts or 0) > 1)

        lines.append(
            "| "
            + " | ".join(
                [
                    safe_cell(job.id),
                    safe_cell(timestamp(job.created_at)),
                    str(job.requested),
                    str(job_counts["done"]),
                    str(job_counts["skipped"]),
                    str(job_counts["failed"]),
                    str(job_counts["queued"]),
                    str(job_counts["running"]),
                    str(job_pages),
                    str(job_retries),
                ]
            )
            + " |"
        )

    lines.extend(["", "### Retry details", ""])

    if retried:
        for item in retried:
            title = item.record.get("title", "Untitled document")
            lines.append(
                f"- Item {item.id}: {safe_cell(title)} (attempts: {item.attempts})"
            )
    else:
        lines.append("- No retried items in the selected jobs.")

    lines.extend(
        [
            "",
            "### Interpretation",
            "",
            "- Ingestion item counts and page totals are read from PostgreSQL.",
            "- Document uniqueness is checked using `external_id`.",
            "- Stored page rows are counted independently from item page totals.",
            (
                "- A job is considered finished when all requested items are in "
                "terminal states and none remain queued or running."
            ),
        ]
    )

    return "\n".join(lines)


def update_report(generated_section: str) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    if REPORT_PATH.exists():
        content = REPORT_PATH.read_text(encoding="utf-8")
    else:
        content = "# Day 10 â€“ Ingestion Queue and Worker Report\n"

    start_count = content.count(START)
    end_count = content.count(END)

    if start_count != end_count or start_count > 1:
        raise ValueError(
            "Report markers are missing, duplicated or unbalanced. "
            "Manual report content was not changed."
        )

    generated_block = f"{START}\n\n{generated_section}\n\n{END}"

    if start_count == 1:
        start_index = content.index(START)
        end_index = content.index(END)

        if end_index < start_index:
            raise ValueError("Report markers are in the wrong order.")

        end_index += len(END)

        content = content[:start_index] + generated_block + content[end_index:]

    else:
        learnt_heading = re.search(
            r"(?im)^#{1,6}\s*what i learnt\s*$",
            content,
        )

        if learnt_heading:
            insert_at = learnt_heading.start()
            content = (
                content[:insert_at].rstrip()
                + "\n\n"
                + generated_block
                + "\n\n"
                + content[insert_at:]
            )
        else:
            content = (
                content.rstrip()
                + "\n\n"
                + generated_block
                + "\n\n## What I learnt\n\n"
                + "<!-- Add personal learning observations here. -->\n"
            )

    REPORT_PATH.write_text(content.rstrip() + "\n", encoding="utf-8")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the ingestion report from PostgreSQL."
    )
    parser.add_argument(
        "--job-id",
        help="Optionally report only one ingestion job.",
    )
    args = parser.parse_args()

    data = await collect_data(args.job_id)
    generated = render_generated_section(data)
    update_report(generated)

    print(f"Report generated: {REPORT_PATH}")
    print(f"Jobs included: {len(data['jobs'])}")
    print(f"Items included: {len(data['items'])}")
    print(
        "Document count:",
        data["document_count"],
        "| Distinct external IDs:",
        data["distinct_external_ids"],
    )


if __name__ == "__main__":
    asyncio.run(main())
