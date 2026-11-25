from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from nikshaynavigator.db.feedback import AnswerFeedbackRepository
from nikshaynavigator.db.models import AnswerFeedback, LlmCall
from nikshaynavigator.db.session import make_engine, make_sessionmaker


@pytest.fixture
async def feedback_context(settings):
    engine = make_engine(settings)

    try:
        async with make_sessionmaker(engine)() as session:
            # Keep every test independent.
            await session.execute(delete(AnswerFeedback))
            await session.execute(delete(LlmCall))

            request_id = str(uuid4())

            # Create a real successful LLM call.
            session.add(
                LlmCall(
                    request_id=request_id,
                    provider="gemini",
                    model="test-model",
                    status="ok",
                )
            )
            await session.commit()

            repo = AnswerFeedbackRepository(session)

            yield session, repo, request_id
    finally:
        await engine.dispose()


@pytest.fixture
def settings(database_url):
    from nikshaynavigator.config import Settings

    return Settings(
        app_env="ci",
        database_url=database_url,
        _env_file=None,
    )


async def test_feedback_is_saved_to_postgres(feedback_context):
    session, repo, request_id = feedback_context

    feedback = await repo.create(
        request_id=request_id,
        helpful=True,
        comment="Clear explanation.",
    )

    assert feedback is not None
    assert feedback.helpful is True
    assert feedback.comment == "Clear explanation."

    stored = await session.scalar(
        select(AnswerFeedback).where(AnswerFeedback.request_id == request_id)
    )

    assert stored is not None


async def test_feedback_rejects_unknown_request(feedback_context):
    _, repo, _ = feedback_context

    result = await repo.create(
        request_id=str(uuid4()),
        helpful=True,
    )

    assert result is None


async def test_duplicate_feedback_is_rejected(feedback_context):
    _, repo, request_id = feedback_context

    await repo.create(
        request_id=request_id,
        helpful=True,
    )

    with pytest.raises(IntegrityError):
        await repo.create(
            request_id=request_id,
            helpful=True,
        )


async def test_feedback_summary_uses_database_records(feedback_context):
    _, repo, first_request_id = feedback_context

    second_request_id = str(uuid4())

    # Add another successful LLM call.
    repo.session.add(
        LlmCall(
            request_id=second_request_id,
            provider="gemini",
            model="test-model",
            status="ok",
        )
    )
    await repo.session.commit()

    await repo.create(
        request_id=first_request_id,
        helpful=True,
    )

    await repo.create(
        request_id=second_request_id,
        helpful=False,
        issue_category="missing_citation",
    )

    summary = await repo.summary()

    assert summary["total"] == 2
    assert summary["helpful"] == 1
    assert summary["not_helpful"] == 1
    assert summary["categories"]["missing_citation"] == 1
