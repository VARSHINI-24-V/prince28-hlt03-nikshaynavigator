from fastapi.testclient import TestClient

from nikshaynavigator.main import app

client = TestClient(app)


def test_list_documents():
    response = client.get("/v1/documents")

    assert response.status_code == 200
    assert response.json()["total"] == 5
    assert len(response.json()["items"]) == 5


def test_search_documents():
    response = client.get("/v1/documents?q=diagnosis")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == "drtb-2025-diagnosis"


def test_document_pagination():
    response = client.get("/v1/documents?skip=1&limit=1")

    assert response.status_code == 200
    assert response.json()["total"] == 5
    assert len(response.json()["items"]) == 1
    assert response.json()["items"][0]["id"] == "drtb-2025-regimen-selection"


def test_get_document():
    response = client.get("/v1/documents/drtb-2025-diagnosis")

    assert response.status_code == 200
    assert response.json()["id"] == "drtb-2025-diagnosis"


def test_document_not_found():
    response = client.get("/v1/documents/448")

    assert response.status_code == 404
    assert response.json()["status"] == 404
    assert response.json()["title"] == "Not Found"


def test_invalid_pagination():
    response = client.get("/v1/documents?skip=-1")

    assert response.status_code == 422
    assert response.json()["status"] == 422
    assert response.json()["title"] == "Unprocessable Content"


def test_request_id_header():
    response = client.get("/health")

    assert response.status_code == 200
    assert "X-Request-Id" in response.headers
    assert len(response.headers["X-Request-Id"]) > 0


def test_request_timing_header():
    response = client.get("/health")

    assert response.status_code == 200
    assert "X-Process-Time-Ms" in response.headers
    assert float(response.headers["X-Process-Time-Ms"]) >= 0
