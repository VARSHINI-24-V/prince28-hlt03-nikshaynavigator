import uuid
from types import SimpleNamespace

import pytest
from arq import Retry
from sqlalchemy import delete

from nikshaynavigator.config import Settings
from nikshaynavigator.db.ingest_jobs import IngestRepository
from nikshaynavigator.db.models import Document, IngestItem, IngestJob
from nikshaynavigator.db.session import make_engine, make_sessionmaker
from nikshaynavigator.workers import ingest as ingest_worker
from nikshaynavigator.workers.ingest import Permanent, ingest_document


async def test_dead_letter_excludes_successfully_ingested_document(
    database_url,
):
    settings = Settings(
        app_env="ci",
        database_url=database_url,
        _env_file=None,
    )

    engine = make_engine(settings)
    session_factory = make_sessionmaker(engine)

    job_id = uuid.uuid4().hex
    resolved_sha = uuid.uuid4().hex * 2
    unresolved_sha = uuid.uuid4().hex * 2

    resolved_item_id = None
    unresolved_item_id = None

    try:
        async with session_factory() as session, session.begin():
            session.add(
                IngestJob(
                    id=job_id,
                    requested=2,
                )
            )

            resolved_item = IngestItem(
                job_id=job_id,
                record={
                    "sha256": resolved_sha,
                    "title": "Successfully retried guideline",
                    "source": "ctd",
                },
                status="failed",
                attempts=1,
                error="parse: ocr_failed",
                pages=0,
            )

            unresolved_item = IngestItem(
                job_id=job_id,
                record={
                    "sha256": unresolved_sha,
                    "title": "Permanently failed guideline",
                    "source": "ctd",
                },
                status="failed",
                attempts=3,
                error="parse: no_text_layer",
                pages=0,
            )

            document = Document(
                external_id=resolved_sha,
                title="Successfully retried guideline",
                source_url="https://example.com/retried.pdf",
                licence="Test licence",
                doc_type="pdf",
                sha256=resolved_sha,
            )

            session.add_all([resolved_item, unresolved_item, document])
            await session.flush()

            resolved_item_id = resolved_item.id
            unresolved_item_id = unresolved_item.id

        repository = IngestRepository(session_factory)
        dead_letters = await repository.dead_letter(limit=50)

        dead_letter_ids = {item["item_id"] for item in dead_letters}

        assert resolved_item_id not in dead_letter_ids
        assert unresolved_item_id in dead_letter_ids

        # The historical failure must remain unchanged.
        async with session_factory() as session:
            original = await session.get(
                IngestItem,
                resolved_item_id,
            )

            assert original is not None
            assert original.status == "failed"
            assert original.error == "parse: ocr_failed"

    finally:
        async with session_factory() as session, session.begin():
            await session.execute(delete(IngestItem).where(IngestItem.job_id == job_id))
            await session.execute(delete(IngestJob).where(IngestJob.id == job_id))
            await session.execute(
                delete(Document).where(Document.external_id == resolved_sha)
            )

        await engine.dispose()


async def create_worker_test_item(session_factory):
    repository = IngestRepository(session_factory)

    job_id, item_ids = await repository.create(
        [
            {
                "sha256": uuid.uuid4().hex * 2,
                "title": "Worker integration test",
                "source": "ctd",
                "url": "https://example.com/test.pdf",
            }
        ]
    )

    context = {
        "settings": SimpleNamespace(ingest_max_tries=3),
        "sessionmaker": session_factory,
    }

    return job_id, item_ids[0], context


async def cleanup_worker_test(engine, session_factory, job_id):
    async with session_factory() as session, session.begin():
        await session.execute(delete(IngestItem).where(IngestItem.job_id == job_id))
        await session.execute(delete(IngestJob).where(IngestJob.id == job_id))

    await engine.dispose()


async def test_worker_persists_success_and_ignores_duplicate_delivery(
    database_url, monkeypatch
):
    settings = Settings(app_env="ci", database_url=database_url, _env_file=None)
    engine = make_engine(settings)
    session_factory = make_sessionmaker(engine)

    job_id, item_id, context = await create_worker_test_item(session_factory)
    calls = 0

    async def fake_process(ctx, session, item):
        nonlocal calls
        calls += 1
        return "done", 12

    monkeypatch.setattr(ingest_worker, "process", fake_process)

    try:
        assert await ingest_document(context, item_id) == "done"

        # A duplicate delivery must not process an already completed item.
        assert await ingest_document(context, item_id) == "ignored"

        async with session_factory() as session:
            item = await session.get(IngestItem, item_id)

            assert item.status == "done"
            assert item.attempts == 1
            assert item.pages == 12
            assert item.error == ""

        assert calls == 1

    finally:
        await cleanup_worker_test(engine, session_factory, job_id)


async def test_worker_persists_retry_and_recovers_on_next_attempt(
    database_url, monkeypatch
):
    settings = Settings(app_env="ci", database_url=database_url, _env_file=None)
    engine = make_engine(settings)
    session_factory = make_sessionmaker(engine)

    job_id, item_id, context = await create_worker_test_item(session_factory)
    calls = 0

    async def fake_process(ctx, session, item):
        nonlocal calls
        calls += 1

        if calls == 1:
            raise RuntimeError("temporary storage failure")

        return "done", 7

    monkeypatch.setattr(ingest_worker, "process", fake_process)

    try:
        with pytest.raises(Retry):
            await ingest_document(context, item_id)

        async with session_factory() as session:
            item = await session.get(IngestItem, item_id)

            assert item.status == "queued"
            assert item.attempts == 1
            assert "temporary storage failure" in item.error

        # Simulate the worker receiving the retried item.
        assert await ingest_document(context, item_id) == "done"

        async with session_factory() as session:
            item = await session.get(IngestItem, item_id)

            assert item.status == "done"
            assert item.attempts == 2
            assert item.pages == 7

    finally:
        await cleanup_worker_test(engine, session_factory, job_id)


async def test_worker_persists_permanent_failure_in_dead_letter(
    database_url, monkeypatch
):
    settings = Settings(app_env="ci", database_url=database_url, _env_file=None)
    engine = make_engine(settings)
    session_factory = make_sessionmaker(engine)

    job_id, item_id, context = await create_worker_test_item(session_factory)

    async def fake_process(ctx, session, item):
        raise Permanent("parse: no_text_layer")

    monkeypatch.setattr(ingest_worker, "process", fake_process)

    try:
        assert await ingest_document(context, item_id) == "failed"

        async with session_factory() as session:
            item = await session.get(IngestItem, item_id)

            assert item.status == "failed"
            assert item.attempts == 1
            assert "parse: no_text_layer" in item.error

        repository = IngestRepository(session_factory)
        dead_letters = await repository.dead_letter(limit=50)

        assert any(entry["item_id"] == item_id for entry in dead_letters)

    finally:
        await cleanup_worker_test(engine, session_factory, job_id)
