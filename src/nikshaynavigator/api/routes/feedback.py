"""API endpoints for answer feedback and feedback analytics."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.exc import IntegrityError

from nikshaynavigator.api.deps import FeedbackDep

router = APIRouter(tags=["feedback"])

IssueCategory = Literal[
    "incorrect_information",
    "outdated_guideline",
    "missing_citation",
    "unclear_answer",
    "other",
]


class FeedbackRequest(BaseModel):
    request_id: UUID
    helpful: bool
    issue_category: IssueCategory | None = None
    comment: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_feedback(self):
        if not self.helpful and self.issue_category is None:
            raise ValueError("An issue category is required for negative feedback.")

        if self.helpful and self.issue_category is not None:
            raise ValueError("An issue category is not allowed for positive feedback.")

        return self


class FeedbackResponse(BaseModel):
    id: int
    request_id: str
    helpful: bool
    issue_category: str | None
    created_at: str


@router.post("/feedback", status_code=201)
async def submit_feedback(
    body: FeedbackRequest,
    repo: FeedbackDep,
) -> dict:
    """Submit feedback for a previously generated answer."""

    try:
        feedback = await repo.create(
            request_id=str(body.request_id),
            helpful=body.helpful,
            issue_category=body.issue_category,
            comment=body.comment,
        )

    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="Feedback has already been submitted for this request.",
        ) from exc

    if feedback is None:
        raise HTTPException(
            status_code=404,
            detail="No successful answer found for this request ID.",
        )

    return {
        "id": feedback.id,
        "request_id": feedback.request_id,
        "helpful": feedback.helpful,
        "issue_category": feedback.issue_category,
        "created_at": feedback.created_at.isoformat(),
        "message": "Feedback submitted successfully.",
    }


@router.get("/feedback/summary")
async def feedback_summary(repo: FeedbackDep) -> dict:
    """Return aggregated user feedback without exposing comments."""

    return await repo.summary()
