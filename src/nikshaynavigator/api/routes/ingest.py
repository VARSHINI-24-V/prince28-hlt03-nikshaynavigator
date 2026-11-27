"""API endpoints for starting and tracking document ingestion."""

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator

from nikshaynavigator.api.deps import (
    IngestRepoDep,
    ManifestDep,
    QueueDep,
    require_admin,
)
from nikshaynavigator.workers.ingest import plan

router = APIRouter(prefix="/ingest", tags=["ingest"])


class IngestRequest(BaseModel):
    """Parameters for starting a document ingestion job."""

    limit: int = Field(default=20, ge=1, le=2000)
    source: str = Field(default="", max_length=100)
    retry_failed: bool = False
    sha256s: list[str] = Field(default_factory=list, max_length=2000)

    @field_validator("sha256s")
    @classmethod
    def validate_sha256s(cls, values: list[str]) -> list[str]:
        """Normalize and validate explicit document hashes."""

        normalized = [value.strip().lower() for value in values]

        if any(re.fullmatch(r"[0-9a-f]{64}", value) is None for value in normalized):
            raise ValueError(
                "Every SHA-256 value must contain exactly 64 hex characters."
            )

        if len(set(normalized)) != len(normalized):
            raise ValueError("Duplicate SHA-256 values are not allowed.")

        return normalized


@router.post(
    "",
    status_code=202,
    dependencies=[Depends(require_admin)],
)
async def start(
    body: IngestRequest,
    response: Response,
    repo: IngestRepoDep,
    queue: QueueDep,
    manifest: ManifestDep,
) -> dict:
    """Create a job, queue its items and return immediately."""

    if body.retry_failed and body.sha256s:
        raise HTTPException(
            status_code=422,
            detail="Explicit SHA-256 selection cannot be combined with retry_failed.",
        )

    if body.retry_failed:
        records = (await repo.failed_records())[: body.limit]

    elif body.sha256s:
        # Build a lookup using only successfully downloaded manifest records.
        by_hash = {}

        for record in manifest:
            doc_hash = str(record.get("sha256", "")).lower()

            if record.get("status") == "downloaded" and doc_hash in body.sha256s:
                by_hash.setdefault(doc_hash, record)

        missing = [doc_hash for doc_hash in body.sha256s if doc_hash not in by_hash]

        if missing:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Some requested hashes are not downloaded manifest records.",
                    "missing_sha256s": missing,
                },
            )

        selected = [by_hash[doc_hash] for doc_hash in body.sha256s]

        if body.source and any(
            record.get("source") != body.source for record in selected
        ):
            raise HTTPException(
                status_code=422,
                detail="A requested document does not match the specified source.",
            )

        known = {str(value).lower() for value in await repo.known_ids() if value}

        # Preserve the explicit request order and avoid known documents.
        records = [
            record for record in selected if record["sha256"].lower() not in known
        ]

    else:
        known = await repo.known_ids()

        records = plan(
            manifest,
            known,
            source=body.source,
            limit=body.limit,
        )

    if not records:
        response.status_code = 200

        return {
            "job_id": None,
            "queued": 0,
            "detail": "Nothing to do: all of it is ingested.",
        }

    job_id, item_ids = await repo.create(records)

    await queue.put(item_ids)

    return {
        "job_id": job_id,
        "queued": len(item_ids),
        "status_url": f"/v1/ingest/{job_id}",
        "documents": [
            {
                "title": record.get("title", "Untitled"),
                "sha256": record["sha256"],
            }
            for record in records
        ],
    }


@router.get("/dead-letter")
async def dead_letter(
    repo: IngestRepoDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict:
    """Return permanently failed ingestion items."""

    items = await repo.dead_letter(limit=limit)

    return {
        "count": len(items),
        "items": items,
    }


@router.get("/{job_id}")
async def progress(
    job_id: str,
    repo: IngestRepoDep,
) -> dict:
    """Return the current progress of an ingestion job."""

    found = await repo.progress(job_id)

    if found is None:
        raise HTTPException(
            status_code=404,
            detail=f"No ingest job with id {job_id!r}.",
        )

    return found
