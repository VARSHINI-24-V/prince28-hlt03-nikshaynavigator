"""Document listing and retrieval endpoints."""

import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from nikshaynavigator.api.deps import get_repo
from nikshaynavigator.db.repository import DocumentRepository

router = APIRouter(prefix="/v1/documents", tags=["Documents"])

RepositoryDependency = Annotated[
    DocumentRepository,
    Depends(get_repo),
]

FILTER_KEY = re.compile(r"^[a-z_][a-z0-9_]{0,40}$")


@router.get("")
async def list_documents(
    request: Request,
    repo: RepositoryDependency,
    q: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    sort_by: str = Query(default="external_id"),
    order: str = Query(default="asc"),
) -> dict[str, Any]:
    """List documents with search, metadata filters and pagination."""

    reserved = {"q", "skip", "limit", "sort_by", "order"}
    allowed_sort_fields = {"external_id", "title", "published_on"}

    if sort_by not in allowed_sort_fields:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort field: {sort_by}",
        )

    if order not in {"asc", "desc"}:
        raise HTTPException(
            status_code=400,
            detail="Invalid sort order. Use 'asc' or 'desc'.",
        )

    filters: dict[str, str] = {}

    for key, value in request.query_params.multi_items():
        if key in reserved:
            continue

        if not FILTER_KEY.fullmatch(key):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid filter name: {key}",
            )

        filters[key] = value

    total, items = await repo.list(
        q=q,
        filters=filters,
        limit=limit,
        offset=skip,
        sort_by=sort_by,
        order=order,
    )

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": items,
        "filters": filters,
    }


@router.get("/{document_id}")
async def get_document(
    document_id: str,
    repo: RepositoryDependency,
) -> dict[str, Any]:
    """Retrieve one document by its ID."""

    document = await repo.get(document_id)

    if document is None:
        raise HTTPException(
            status_code=404,
            detail=f"Document '{document_id}' not found",
        )

    return document
