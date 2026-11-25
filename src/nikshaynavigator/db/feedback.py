"""Database operations for answer feedback."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nikshaynavigator.db.models import AnswerFeedback, LlmCall


class AnswerFeedbackRepository:
    """Store feedback and retrieve feedback analytics."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        request_id: str,
        helpful: bool,
        issue_category: str | None = None,
        comment: str | None = None,
    ) -> AnswerFeedback | None:
        """Save feedback only when a successful LLM answer exists."""

        answer_id = await self.session.scalar(
            select(LlmCall.id)
            .where(
                LlmCall.request_id == request_id,
                LlmCall.status == "ok",
            )
            .limit(1)
        )

        if answer_id is None:
            return None

        feedback = AnswerFeedback(
            request_id=request_id,
            helpful=helpful,
            issue_category=issue_category,
            comment=comment,
        )

        self.session.add(feedback)

        try:
            await self.session.commit()
            await self.session.refresh(feedback)
        except Exception:
            await self.session.rollback()
            raise

        return feedback

    async def summary(self) -> dict[str, Any]:
        """Return rating totals and counts for each issue category."""

        rating_stmt = select(
            AnswerFeedback.helpful,
            func.count(AnswerFeedback.id).label("count"),
        ).group_by(AnswerFeedback.helpful)

        rating_result = await self.session.execute(rating_stmt)

        ratings = {bool(row.helpful): row.count for row in rating_result}

        category_stmt = (
            select(
                AnswerFeedback.issue_category,
                func.count(AnswerFeedback.id).label("count"),
            )
            .where(AnswerFeedback.issue_category.is_not(None))
            .group_by(AnswerFeedback.issue_category)
        )

        category_result = await self.session.execute(category_stmt)

        categories = {row.issue_category: row.count for row in category_result}

        return {
            "total": sum(ratings.values()),
            "helpful": ratings.get(True, 0),
            "not_helpful": ratings.get(False, 0),
            "categories": categories,
        }
