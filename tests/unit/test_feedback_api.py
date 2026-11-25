"""Tests for answer feedback and feedback analytics endpoints."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from nikshaynavigator.api.deps import get_feedback_repo
from nikshaynavigator.main import create_app

VALID_REQUEST_ID = "123e4567-e89b-12d3-a456-426614174000"
UNKNOWN_REQUEST_ID = "123e4567-e89b-12d3-a456-426614174001"


class FakeFeedbackRepository:
    """In-memory feedback repository for API tests."""

    def __init__(self):
        self.records = []

    async def create(
        self,
        *,
        request_id,
        helpful,
        issue_category=None,
        comment=None,
    ):
        if request_id == UNKNOWN_REQUEST_ID:
            return None

        if any(row.request_id == request_id for row in self.records):
            raise IntegrityError(
                "duplicate feedback",
                {},
                Exception("duplicate request_id"),
            )

        feedback = SimpleNamespace(
            id=len(self.records) + 1,
            request_id=request_id,
            helpful=helpful,
            issue_category=issue_category,
            comment=comment,
            created_at=datetime.now(UTC),
        )

        self.records.append(feedback)
        return feedback

    async def summary(self):
        helpful = sum(row.helpful for row in self.records)
        not_helpful = len(self.records) - helpful

        categories = {}

        for row in self.records:
            if row.issue_category:
                categories[row.issue_category] = (
                    categories.get(row.issue_category, 0) + 1
                )

        return {
            "total": len(self.records),
            "helpful": helpful,
            "not_helpful": not_helpful,
            "categories": categories,
        }


@pytest.fixture
def feedback_client():
    app = create_app()
    repository = FakeFeedbackRepository()

    app.dependency_overrides[get_feedback_repo] = lambda: repository

    with TestClient(app) as test_client:
        yield test_client, repository

    app.dependency_overrides.clear()


def test_positive_feedback_is_submitted(feedback_client):
    client, repository = feedback_client

    response = client.post(
        "/v1/feedback",
        json={
            "request_id": VALID_REQUEST_ID,
            "helpful": True,
        },
    )

    assert response.status_code == 201
    assert response.json()["message"] == "Feedback submitted successfully."
    assert response.json()["helpful"] is True
    assert response.json()["issue_category"] is None
    assert len(repository.records) == 1


def test_negative_feedback_is_submitted(feedback_client):
    client, repository = feedback_client

    response = client.post(
        "/v1/feedback",
        json={
            "request_id": VALID_REQUEST_ID,
            "helpful": False,
            "issue_category": "incorrect_information",
            "comment": "The answer did not match the guideline.",
        },
    )

    assert response.status_code == 201
    assert response.json()["helpful"] is False
    assert response.json()["issue_category"] == "incorrect_information"
    assert len(repository.records) == 1


def test_negative_feedback_requires_category(feedback_client):
    client, _ = feedback_client

    response = client.post(
        "/v1/feedback",
        json={
            "request_id": VALID_REQUEST_ID,
            "helpful": False,
        },
    )

    assert response.status_code == 422


def test_feedback_rejects_invalid_category(feedback_client):
    client, _ = feedback_client

    response = client.post(
        "/v1/feedback",
        json={
            "request_id": VALID_REQUEST_ID,
            "helpful": False,
            "issue_category": "wrong_category",
        },
    )

    assert response.status_code == 422


def test_positive_feedback_rejects_issue_category(feedback_client):
    client, _ = feedback_client

    response = client.post(
        "/v1/feedback",
        json={
            "request_id": VALID_REQUEST_ID,
            "helpful": True,
            "issue_category": "missing_citation",
        },
    )

    assert response.status_code == 422


def test_feedback_rejects_unknown_request_id(feedback_client):
    client, _ = feedback_client

    response = client.post(
        "/v1/feedback",
        json={
            "request_id": UNKNOWN_REQUEST_ID,
            "helpful": True,
        },
    )

    assert response.status_code == 404


def test_duplicate_feedback_returns_conflict(feedback_client):
    client, _ = feedback_client

    payload = {
        "request_id": VALID_REQUEST_ID,
        "helpful": True,
    }

    first = client.post("/v1/feedback", json=payload)
    second = client.post("/v1/feedback", json=payload)

    assert first.status_code == 201
    assert second.status_code == 409


def test_feedback_summary_returns_correct_counts(feedback_client):
    client, _ = feedback_client

    client.post(
        "/v1/feedback",
        json={
            "request_id": VALID_REQUEST_ID,
            "helpful": True,
        },
    )

    client.post(
        "/v1/feedback",
        json={
            "request_id": UNKNOWN_REQUEST_ID.replace("001", "002"),
            "helpful": False,
            "issue_category": "missing_citation",
        },
    )

    response = client.get("/v1/feedback/summary")

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 2
    assert data["helpful"] == 1
    assert data["not_helpful"] == 1
    assert data["categories"]["missing_citation"] == 1
