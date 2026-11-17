
from fastapi import FastAPI

from nikshaynavigator.api.health import router as health_router
from nikshaynavigator.config import settings

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="NTEP guideline-based question answering system"
)

app.include_router(health_router)
