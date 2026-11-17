from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError

from nikshaynavigator.api.errors import (
    http_exception_handler,
    validation_exception_handler,
)
from nikshaynavigator.api.middleware import request_tracking_middleware
from nikshaynavigator.api.routes.documents import (
    router as documents_router,
)
from nikshaynavigator.api.routes.health import router as health_router
from nikshaynavigator.config import get_settings
from nikshaynavigator.logging_setup import setup_logging


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="NTEP guideline-based question answering system",
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
