import pytest
from fastapi.testclient import TestClient

from nikshaynavigator.api.deps import check_db
from nikshaynavigator.config import get_settings
from nikshaynavigator.main import create_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("APP_ENV", "ci")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://app:app@localhost:5432/test",  # pragma: allowlist secret
    )
    monkeypatch.setenv("GIT_SHA", "test-sha")

    get_settings.cache_clear()

    app = create_app()
    app.dependency_overrides[check_db] = lambda: True

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_health_endpoint_includes_version(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app": "nikshaynavigator",
        "env": "ci",
        "version": "test-sha",
    }


def test_readiness_endpoint(client):
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": True},
    }
