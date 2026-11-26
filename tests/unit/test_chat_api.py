"""Tests for streaming chat and usage endpoints."""

import json

import pytest
from fastapi.testclient import TestClient

from nikshaynavigator.api.deps import get_gateway, get_usage_repo
from nikshaynavigator.llm.gateway import FakeLLM, LLMGateway
from nikshaynavigator.main import create_app


class FakeUsageRepository:
    async def by_day(self, days=7):
        return [
            {
                "day": "2026-11-25",
                "calls": 2,
                "errors": 0,
                "fallbacks": 1,
                "tokens_in": 100,
                "tokens_out": 50,
                "cost_inr": 0.05,
            }
        ]


@pytest.fixture
def client():
    app = create_app()

    fake = FakeLLM(
        name="gemini",
        model="fake-1",
        script=["docs", "A fake answer."],
    )
    app.state.fake_llm = fake
    gateway = LLMGateway([fake])

    app.dependency_overrides[get_gateway] = lambda: gateway
    app.dependency_overrides[get_usage_repo] = lambda: FakeUsageRepository()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_streaming_chat_returns_sse(client):
    response = client.post(
        "/v1/chat",
        json={"message": "Explain TB", "stream": True},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"delta"' in response.text
    assert "event: done" in response.text

    deltas = []

    for line in response.text.splitlines():
        if line.startswith("data: ") and '"delta"' in line:
            payload = json.loads(line[len("data: ") :])
            deltas.append(payload["delta"])

    assert "".join(deltas).strip() == "A fake answer."


def test_non_streaming_chat_returns_json(client):
    response = client.post(
        "/v1/chat",
        json={"message": "Explain TB", "stream": False},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["answer"] == "A fake answer."
    assert data["provider"] == "gemini"
    assert data["model"] == "fake-1"


def test_chat_rejects_empty_message(client):
    response = client.post(
        "/v1/chat",
        json={"message": "", "stream": True},
    )

    assert response.status_code == 422


def test_chat_rejects_message_over_4000_characters(client):
    response = client.post(
        "/v1/chat",
        json={"message": "A" * 4001},
    )

    assert response.status_code == 422


def test_chat_returns_503_when_no_provider_available(client):
    client.app.dependency_overrides[get_gateway] = lambda: LLMGateway([])

    response = client.post(
        "/v1/chat",
        json={"message": "Explain TB", "stream": True},
    )

    assert response.status_code == 503


def test_usage_returns_daily_totals(client):
    response = client.get("/v1/usage")

    assert response.status_code == 200

    data = response.json()

    assert data["calls"] == 2
    assert data["total_cost_inr"] == 0.05
    assert data["days"][0]["tokens_in"] == 100
    assert data["days"][0]["fallbacks"] == 1


def test_usage_rejects_invalid_days(client):
    response = client.get("/v1/usage?days=0")

    assert response.status_code == 422


def test_docs_question_runs_classifier_and_answer(client):
    response = client.post(
        "/v1/chat",
        json={"message": "What does NTEP recommend?", "stream": False},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["classification"] == "docs"
    assert data["answer"] == "A fake answer."
    assert data["classifier_prompt_version"] == "classify_v4"
    assert client.app.state.fake_llm.calls == 2


def test_personal_question_does_not_generate_second_answer(client):
    fake = FakeLLM(name="gemini", model="fake-1", script=["personal"])
    gateway = LLMGateway([fake])
    client.app.dependency_overrides[get_gateway] = lambda: gateway

    response = client.post(
        "/v1/chat",
        json={"message": "Did patient Ravi take today's dose?", "stream": False},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["classification"] == "personal"
    assert "cannot access" in data["answer"]
    assert fake.calls == 1


def test_off_topic_stream_uses_only_classifier(client):
    fake = FakeLLM(name="gemini", model="fake-1", script=["off_topic"])
    gateway = LLMGateway([fake])
    client.app.dependency_overrides[get_gateway] = lambda: gateway

    response = client.post(
        "/v1/chat",
        json={"message": "Tell me a joke.", "stream": True},
    )

    assert response.status_code == 200
    assert "event: done" in response.text
    assert '"classification": "off_topic"' in response.text
    assert fake.calls == 1


def test_invalid_classifier_output_fails_closed(client):
    fake = FakeLLM(name="gemini", model="fake-1", script=["not-a-label"])
    gateway = LLMGateway([fake])
    client.app.dependency_overrides[get_gateway] = lambda: gateway

    response = client.post(
        "/v1/chat",
        json={"message": "What does NTEP recommend?", "stream": False},
    )

    assert response.status_code == 502
    assert fake.calls == 1
