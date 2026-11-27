"""Redis queue connection, enqueueing and recovery helpers."""

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from arq.jobs import Job, JobStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from nikshaynavigator.config import get_settings
from nikshaynavigator.db.models import IngestItem


async def connect_queue() -> ArqRedis:
    """Create an ARQ Redis connection pool."""

    settings = get_settings()

    return await create_pool(RedisSettings.from_dsn(settings.redis_url))


async def enqueue_document(
    redis: ArqRedis,
    item_id: int,
) -> str:
    """Enqueue one document, recovering stale completed ARQ jobs."""

    job_id = f"ingest-item-{item_id}"

    existing = Job(job_id, redis)
    status = await existing.status()

    # A completed ARQ result must not block recovery when PostgreSQL
    # still says that the ingestion item is queued or running.
    if status == JobStatus.complete:
        await redis.delete(f"arq:result:{job_id}")

    job = await redis.enqueue_job(
        "ingest_document",
        item_id,
        _job_id=job_id,
    )

    return job.job_id if job is not None else job_id


async def enqueue_items(
    redis: ArqRedis,
    item_ids: list[int],
) -> list[str]:
    """Enqueue multiple document items."""

    job_ids = []

    for item_id in item_ids:
        job_ids.append(await enqueue_document(redis, item_id))

    return job_ids


async def recover_unfinished_items(
    redis: ArqRedis,
    sessionmaker: async_sessionmaker,
) -> int:
    """Recover queued or running items from PostgreSQL."""

    async with sessionmaker() as session:
        result = await session.scalars(
            select(IngestItem.id)
            .where(IngestItem.status.in_(["queued", "running"]))
            .order_by(IngestItem.id)
        )

        item_ids = list(result.all())

    await enqueue_items(redis, item_ids)

    return len(item_ids)


async def ping_queue(redis: ArqRedis) -> bool:
    """Check whether Redis is reachable."""

    return bool(await redis.ping())


async def close_queue(redis: ArqRedis) -> None:
    """Close the Redis connection pool."""

    await redis.aclose()


class IngestQueue:
    """Small interface for API routes to enqueue document items."""

    def __init__(self, redis: ArqRedis) -> None:
        self.redis = redis

    async def put(self, item_ids: list[int]) -> list[str]:
        """Enqueue a list of document item IDs."""

        return await enqueue_items(self.redis, item_ids)
