import pytest
from fastapi.testclient import TestClient

from nikshaynavigator.api.deps import check_db
from nikshaynavigator.main import create_app


@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[check_db] = lambda: True

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_readiness_endpoint(client):
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": True},
    }
