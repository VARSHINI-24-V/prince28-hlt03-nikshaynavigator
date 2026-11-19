from fastapi.testclient import TestClient

from nikshaynavigator.main import create_app


def test_database_pool_metrics():
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/metrics/db-pool")

    assert response.status_code == 200

    data = response.json()

    assert data["pool_size"] == 5
    assert data["max_overflow"] == 2
    assert data["max_connections"] == 7
    assert "checked_out" in data
    assert "checked_in" in data
    assert "overflow" in data
    assert data["status"] == "available"


def test_database_pool_metrics_without_engine():
    app = create_app()

    with TestClient(app) as client:
        app.state.engine = None
        response = client.get("/metrics/db-pool")

    assert response.status_code == 503
    assert response.json()["detail"] == "Database engine is unavailable"
