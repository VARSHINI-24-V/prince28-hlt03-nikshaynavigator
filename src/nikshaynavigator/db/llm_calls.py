"""Database operations for LLM call records and daily usage."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nikshaynavigator.db.models import LlmCall


class LlmCallRepository:
    """Store LLM calls and retrieve daily usage summaries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(self, call: dict[str, Any]) -> None:
        """Save one LLM call to PostgreSQL."""
        self.session.add(LlmCall(**call))

        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def by_day(self, days: int = 7) -> list[dict[str, Any]]:
        """Aggregate calls, tokens and costs by day."""
        cutoff = datetime.now(UTC) - timedelta(days=days)

        day_column = func.date(LlmCall.created_at).label("day")

        stmt = (
            select(
                day_column,
                func.count(LlmCall.id).label("calls"),
                func.sum(
                    case(
                        (LlmCall.status == "error", 1),
                        else_=0,
                    )
                ).label("errors"),
                func.sum(
                    case(
                        (LlmCall.fallback_used.is_(True), 1),
                        else_=0,
                    )
                ).label("fallbacks"),
                func.coalesce(func.sum(LlmCall.tokens_in), 0).label("tokens_in"),
                func.coalesce(func.sum(LlmCall.tokens_out), 0).label("tokens_out"),
                func.coalesce(func.sum(LlmCall.cost_inr), 0).label("cost_inr"),
            )
            .where(LlmCall.created_at >= cutoff)
            .group_by(day_column)
            .order_by(day_column.desc())
        )

        result = await self.session.execute(stmt)

        return [
            {
                "day": row.day.isoformat(),
                "calls": row.calls,
                "errors": row.errors,
                "fallbacks": row.fallbacks,
                "tokens_in": row.tokens_in,
                "tokens_out": row.tokens_out,
                "cost_inr": float(row.cost_inr),
            }
            for row in result
        ]
