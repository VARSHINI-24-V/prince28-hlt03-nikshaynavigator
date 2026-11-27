import uuid

from sqlalchemy import delete

from nikshaynavigator.config import Settings
from nikshaynavigator.db.ingest_jobs import IngestRepository
from nikshaynavigator.db.models import Document, IngestItem, IngestJob
from nikshaynavigator.db.session import make_engine, make_sessionmaker


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
