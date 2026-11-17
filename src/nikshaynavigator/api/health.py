from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health_check():
    return {"status": "healthy", "service": "NikshayNavigator"}


@router.get("/ready")
def readiness_check():
    return {"status": "ready", "guidelines_loaded": False}
