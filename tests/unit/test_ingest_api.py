"""Tests for ingestion API endpoints."""

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError

from nikshaynavigator.api.deps import (
    get_ingest_repo,
    get_manifest,
    get_queue,
)
from nikshaynavigator.config import get_settings
from nikshaynavigator.main import create_app

ADMIN_TOKEN = "test-admin-token"

RECORD = {
    "url": "https://example.com/guideline.pdf",
    "source": "ctd",
    "licence": "Government publication",
    "title": "TB Guideline",
    "path": "data/raw/ctd/guideline.pdf",
    "sha256": "a" * 64,
    "status": "downloaded",
}


class FakeIngestRepository:
    """In-memory repository for ingestion API tests."""

    def __init__(self):
        self.created_records = []
        self.failed = [dict(RECORD)]
        self.dead_items = [
            {
                "item_id": 10,
                "job_id": "old-job",
                "title": "Failed guideline",
                "status": "failed",
                "attempts": 3,
                "error": "parse: no_text_layer",
            }
        ]
        self.progress_result = {
            "job_id": "test-job",
            "requested": 2,
            "queued": 0,
            "running": 1,
            "done": 1,
            "skipped": 0,
            "failed": 0,
            "pages": 12,
            "finished": False,
        }

    async def known_ids(self):
        return set()

    async def create(self, records):
        self.created_records = list(records)

        item_ids = list(range(101, 101 + len(records)))

        return "test-job", item_ids

    async def failed_records(self):
        return list(self.failed)

    async def dead_letter(self, limit=50):
        return self.dead_items[:limit]

    async def progress(self, job_id):
        if job_id == "test-job":
            return self.progress_result

        return None


class FakeQueue:
    """Fake Redis queue that records submitted item IDs."""

    def __init__(self):
        self.submitted = []

    async def put(self, item_ids):
        self.submitted.extend(item_ids)


@pytest.fixture
def ingest_client(monkeypatch):
    """Create an API client with fake ingestion dependencies."""

    monkeypatch.setenv("APP_ENV", "ci")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://app:app@localhost:5432/test",  # pragma: allowlist secret
    )
    monkeypatch.setenv("ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.setenv("WORKER_IN_API", "false")

    get_settings.cache_clear()

    app = create_app()

    repository = FakeIngestRepository()
    queue = FakeQueue()

    app.dependency_overrides[get_ingest_repo] = lambda: repository
    app.dependency_overrides[get_queue] = lambda: queue
    app.dependency_overrides[get_manifest] = lambda: [dict(RECORD)]

    with TestClient(app) as client:
        yield client, repository, queue

    app.dependency_overrides.clear()
    get_settings.cache_clear()


def admin_headers():
    return {"X-Admin-Token": ADMIN_TOKEN}


def test_ingest_requires_admin_token(ingest_client):
    client, _, _ = ingest_client

    response = client.post(
        "/v1/ingest",
        json={"limit": 1},
    )

    assert response.status_code == 401


def test_ingest_rejects_invalid_admin_token(ingest_client):
    client, _, _ = ingest_client

    response = client.post(
        "/v1/ingest",
        json={"limit": 1},
        headers={"X-Admin-Token": "wrong-token"},
    )

    assert response.status_code == 401


def test_ingest_creates_job_and_queues_items(ingest_client):
    client, repository, queue = ingest_client

    response = client.post(
        "/v1/ingest",
        json={"limit": 10},
        headers=admin_headers(),
    )

    assert response.status_code == 202
    assert response.json()["job_id"] == "test-job"
    assert response.json()["queued"] == 1
    assert response.json()["status_url"] == "/v1/ingest/test-job"

    assert len(repository.created_records) == 1
    assert queue.submitted == [101]


def test_ingest_returns_200_when_nothing_needs_processing(
    ingest_client,
):
    client, repository, _ = ingest_client

    def empty_manifest():
        return []

    client.app.dependency_overrides[get_manifest] = empty_manifest

    response = client.post(
        "/v1/ingest",
        json={"limit": 10},
        headers=admin_headers(),
    )

    assert response.status_code == 200
    assert response.json()["queued"] == 0
    assert repository.created_records == []


def test_ingest_can_retry_failed_items(ingest_client):
    client, repository, queue = ingest_client

    response = client.post(
        "/v1/ingest",
        json={"limit": 5, "retry_failed": True},
        headers=admin_headers(),
    )

    assert response.status_code == 202
    assert response.json()["queued"] == 1
    assert len(repository.created_records) == 1
    assert queue.submitted == [101]


def test_ingest_progress_returns_job_status(ingest_client):
    client, _, _ = ingest_client

    response = client.get("/v1/ingest/test-job")

    assert response.status_code == 200
    assert response.json()["running"] == 1
    assert response.json()["done"] == 1
    assert response.json()["pages"] == 12
    assert response.json()["finished"] is False


def test_ingest_progress_returns_404_for_unknown_job(
    ingest_client,
):
    client, _, _ = ingest_client

    response = client.get("/v1/ingest/unknown-job")

    assert response.status_code == 404


def test_dead_letter_returns_failed_items(ingest_client):
    client, _, _ = ingest_client

    response = client.get("/v1/ingest/dead-letter")

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["items"][0]["error"] == ("parse: no_text_layer")


def test_ingest_returns_503_when_redis_is_unavailable(
    ingest_client,
    monkeypatch,
):
    client, _, _ = ingest_client

    # Use the real queue dependency for this test.
    client.app.dependency_overrides.pop(get_queue)

    async def broken_connect():
        raise RedisConnectionError("Redis connection refused")

    monkeypatch.setattr(
        "nikshaynavigator.api.deps.connect_queue",
        broken_connect,
    )

    response = client.post(
        "/v1/ingest",
        json={"limit": 1},
        headers=admin_headers(),
    )

    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"]


def test_ingest_accepts_explicit_sha256_selection(ingest_client):
    client, repository, queue = ingest_client

    response = client.post(
        "/v1/ingest",
        json={"sha256s": ["a" * 64]},
        headers=admin_headers(),
    )

    assert response.status_code == 202
    assert response.json()["queued"] == 1
    assert repository.created_records == [RECORD]
    assert queue.submitted == [101]
    assert response.json()["documents"][0]["sha256"] == "a" * 64


def test_ingest_rejects_unknown_explicit_sha256(ingest_client):
    client, repository, queue = ingest_client

    response = client.post(
        "/v1/ingest",
        json={"sha256s": ["b" * 64]},
        headers=admin_headers(),
    )

    assert response.status_code == 422
    assert repository.created_records == []
    assert queue.submitted == []
