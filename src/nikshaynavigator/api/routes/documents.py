from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from nikshaynavigator.api.deps import get_documents

router = APIRouter(prefix="/v1/documents", tags=["Documents"])

DocumentsDependency = Annotated[
    list[dict[str, Any]],
    Depends(get_documents),
]


@router.get("")
def list_documents(
    documents: DocumentsDependency,
    q: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """List guideline documents with optional search and pagination."""

    if q:
        search_term = q.lower()
        documents = [
            document
            for document in documents
            if search_term
            in " ".join(str(value) for value in document.values()).lower()
        ]

    total = len(documents)
    items = documents[skip : skip + limit]

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": items,
    }


@router.get("/{document_id}")
def get_document(
    document_id: str,
    documents: DocumentsDependency,
) -> dict[str, Any]:
    """Retrieve one guideline document by its ID."""

    for document in documents:
        if document.get("id") == document_id:
            return document

    raise HTTPException(
        status_code=404,
        detail=f"Document '{document_id}' not found",
    )
