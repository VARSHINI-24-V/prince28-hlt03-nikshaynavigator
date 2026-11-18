import pytest
from fastapi.testclient import TestClient

from nikshaynavigator.api.deps import get_repo
from nikshaynavigator.main import create_app

DOCUMENTS = [
    {"id": "drtb-2025-overview", "title": "DR-TB overview"},
    {
        "id": "drtb-2025-regimen-selection",
        "title": "DR-TB regimen selection",
    },
    {
        "id": "drtb-2025-diagnosis",
        "title": "DR-TB diagnosis guidelines",
        "topic": "Drug-resistant TB diagnosis",
    },
    {"id": "drtb-2025-treatment", "title": "DR-TB treatment"},
    {"id": "drtb-2025-followup", "title": "DR-TB follow-up"},
]


class FakeRepository:
    async def list(self, *, q, filters, limit, offset):
        records = DOCUMENTS.copy()

        if q:
            records = [
                doc
                for doc in records
                if q.lower() in " ".join(str(v) for v in doc.values()).lower()
            ]

        for key, value in filters.items():
            records = [doc for doc in records if str(doc.get(key)) == value]

        total = len(records)
        return total, records[offset : offset + limit]

    async def get(self, external_id):
        return next(
            (doc for doc in DOCUMENTS if doc["id"] == external_id),
            None,
        )


@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[get_repo] = lambda: FakeRepository()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_list_documents(client):
    response = client.get("/v1/documents")

    assert response.status_code == 200
    assert response.json()["total"] == 5
    assert len(response.json()["items"]) == 5


def test_search_documents(client):
    response = client.get("/v1/documents?q=diagnosis")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == "drtb-2025-diagnosis"


def test_document_pagination(client):
    response = client.get("/v1/documents?skip=1&limit=1")

    assert response.status_code == 200
    assert response.json()["total"] == 5
    assert len(response.json()["items"]) == 1
    assert response.json()["items"][0]["id"] == "drtb-2025-regimen-selection"


def test_get_document(client):
    response = client.get("/v1/documents/drtb-2025-diagnosis")

    assert response.status_code == 200
    assert response.json()["id"] == "drtb-2025-diagnosis"


def test_document_not_found(client):
    response = client.get("/v1/documents/448")

    assert response.status_code == 404
    assert response.json()["status"] == 404
    assert response.json()["title"] == "Not Found"


def test_invalid_pagination(client):
    response = client.get("/v1/documents?skip=-1")

    assert response.status_code == 422
    assert response.json()["status"] == 422
    assert response.json()["title"] == "Unprocessable Content"


def test_request_id_header(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert "X-Request-Id" in response.headers
    assert len(response.headers["X-Request-Id"]) > 0


def test_request_timing_header(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert "X-Process-Time-Ms" in response.headers
    assert float(response.headers["X-Process-Time-Ms"]) >= 0


def test_metadata_filter(client):
    response = client.get("/v1/documents?topic=Drug-resistant%20TB%20diagnosis")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["filters"] == {"topic": "Drug-resistant TB diagnosis"}
    assert response.json()["items"][0]["id"] == "drtb-2025-diagnosis"


def test_invalid_metadata_filter(client):
    response = client.get("/v1/documents?Bad-Name=1")

    assert response.status_code == 400
    assert "Invalid filter name" in response.json()["detail"]
