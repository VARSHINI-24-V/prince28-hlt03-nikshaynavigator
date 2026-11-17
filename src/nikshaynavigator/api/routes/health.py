from fastapi import APIRouter

from nikshaynavigator.store import load_documents

router = APIRouter()


@router.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "NikshayNavigator",
    }


@router.get("/ready")
def readiness_check():
    documents = load_documents()

    return {
        "status": "ready",
        "guidelines_loaded": len(documents) > 0,
        "guideline_count": len(documents),
    }
