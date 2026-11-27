"""ARQ worker configuration and application lifecycle."""

import asyncio
import logging
from typing import ClassVar
from uuid import uuid4

import httpx
from arq.connections import RedisSettings

from nikshaynavigator.config import get_settings
from nikshaynavigator.db.llm_calls import LlmCallRepository
from nikshaynavigator.db.session import make_engine, make_sessionmaker
from nikshaynavigator.ingest.fetch import make_client
from nikshaynavigator.llm.doc_meta import DocMeta
from nikshaynavigator.llm.extract import LLMGateway
from nikshaynavigator.llm.gateway import build_gateway
from nikshaynavigator.llm.prompts import find_prompts, load_prompt
from nikshaynavigator.workers.ingest import Pace, ingest_document
from nikshaynavigator.workers.queue import recover_unfinished_items

logger = logging.getLogger("nikshaynavigator.worker")


async def startup(ctx: dict) -> None:
    """Create shared resources and recover unfinished work."""

    settings = get_settings()

    engine = make_engine(settings)
    sessionmaker = make_sessionmaker(engine)
    http = make_client(settings.ingest_concurrency)

    async def record_llm_call(row: dict) -> None:
        """Persist metadata extraction model usage."""

        call = dict(row)
        call["request_id"] = call.get("request_id") or str(uuid4())

        async with sessionmaker() as session:
            await LlmCallRepository(session).record(call)

    gateway = build_gateway(
        settings,
        recorder=record_llm_call,
    )

    # Set extraction only when both a prompt and a model provider exist.
    versions = find_prompts("extract", settings.prompts_dir)
    extraction = None

    if versions and gateway.providers:
        version = versions[-1]

        extraction = {
            "schema": DocMeta,
            "prompt": load_prompt(version, settings.prompts_dir),
            "version": version,
            "chars": 6000,
        }
        logger.info("Metadata extraction enabled: %s", version)
    else:
        logger.warning(
            "Metadata extraction disabled: prompt or model provider unavailable"
        )

    # Store shared application resources in ARQ's job context.
    ctx["settings"] = settings
    ctx["engine"] = engine
    ctx["sessionmaker"] = sessionmaker
    ctx["http"] = http
    ctx["gateway"] = gateway
    ctx["pace"] = Pace(settings.ingest_rpm)
    ctx["extract"] = extraction
    ctx["parse_lock"] = asyncio.Lock()

    # ARQ creates this Redis connection and exposes it in ctx.
    redis = ctx["redis"]

    recovered = await recover_unfinished_items(
        redis,
        sessionmaker,
    )

    logger.info(
        "Worker ready: %d unfinished item(s) put back in the queue",
        recovered,
    )


async def shutdown(ctx: dict) -> None:
    """Close shared resources when the worker shuts down."""

    http: httpx.AsyncClient | None = ctx.get("http")

    if http is not None:
        await http.aclose()

    gateway: LLMGateway | None = ctx.get("gateway")

    if gateway is not None:
        for provider in gateway.providers:
            client = getattr(provider, "_client", None)

            if client is not None:
                await client.aclose()

    engine = ctx.get("engine")

    if engine is not None:
        await engine.dispose()

    logger.info("Worker resources closed")


class WorkerSettings:
    """Settings consumed by the ARQ command-line worker."""

    settings = get_settings()

    functions: ClassVar[list] = [ingest_document]

    on_startup = startup
    on_shutdown = shutdown

    redis_settings = RedisSettings.from_dsn(settings.redis_url)

    max_jobs = settings.ingest_concurrency
    job_timeout = settings.ingest_job_timeout
    max_tries = settings.ingest_max_tries
