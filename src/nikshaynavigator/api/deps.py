from typing import Any

from nikshaynavigator.store import load_documents


def get_documents() -> list[dict[str, Any]]:
    """Provide guideline documents to API endpoints."""
    return load_documents()
