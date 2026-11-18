from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError

from nikshaynavigator.api.errors import (
    http_exception_handler,
    validation_exception_handler,
)
from nikshaynavigator.api.middleware import request_tracking_middleware
from nikshaynavigator.api.routes.documents import router as documents_router
from nikshaynavigator.api.routes.health import router as health_router
from nikshaynavigator.config import get_settings
from nikshaynavigator.db.session import make_engine, make_sessionmaker
from nikshaynavigator.logging_setup import setup_logging


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging()

    engine = make_engine(settings)
    session_factory = make_sessionmaker(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.engine = engine
        app.state.session_factory = session_factory
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

    return app


app = create_app()
