from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError

from nikshaynavigator.api.errors import (
    http_exception_handler,
    validation_exception_handler,
)
from nikshaynavigator.api.middleware import request_tracking_middleware
from nikshaynavigator.api.routes.chat import (
    load_prompt,
)
from nikshaynavigator.api.routes.chat import (
    router as chat_router,
)
from nikshaynavigator.api.routes.documents import router as documents_router
from nikshaynavigator.api.routes.feedback import (
    router as feedback_router,
)
from nikshaynavigator.api.routes.health import router as health_router
from nikshaynavigator.api.routes.pool_metrics import (
    router as pool_metrics_router,
)
from nikshaynavigator.config import get_settings
from nikshaynavigator.db.llm_calls import LlmCallRepository
from nikshaynavigator.db.session import make_engine, make_sessionmaker
from nikshaynavigator.llm.gateway import build_gateway
from nikshaynavigator.logging_setup import setup_logging


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging()

    engine = make_engine(settings)
    session_factory = make_sessionmaker(engine)

    system_prompt = load_prompt(settings.prompts_dir)

    async def record_llm_call(row: dict) -> None:
        """Persist each LLM call in PostgreSQL."""
        async with session_factory() as session:
            repository = LlmCallRepository(session)
            await repository.record(row)

    gateway = build_gateway(
        settings,
        recorder=record_llm_call,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.engine = engine
        app.state.session_factory = session_factory
        app.state.gateway = gateway
        app.state.system_prompt = system_prompt

        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="NTEP guideline-based question answering system",
        lifespan=lifespan,
    )

    app.add_exception_handler(
        HTTPException,
        http_exception_handler,
    )
    app.add_exception_handler(
        RequestValidationError,
        validation_exception_handler,
    )

    app.middleware("http")(request_tracking_middleware)

    app.include_router(health_router)
    app.include_router(documents_router)
    app.include_router(pool_metrics_router)
    app.include_router(chat_router, prefix="/v1")
    app.include_router(feedback_router, prefix="/v1")

    return app


app = create_app()
