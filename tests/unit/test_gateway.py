"""Unit tests for the LLM gateway. No real API calls or bills."""

import httpx
import pytest

from nikshaynavigator.llm.gateway import (
    CircuitBreaker,
    FakeLLM,
    LLMError,
    LLMGateway,
    LLMResult,
    LLMUnavailable,
    OpenAICompatProvider,
    cost_inr,
    estimate_tokens,
)
from nikshaynavigator.logging_setup import request_id_ctx


async def no_sleep(seconds: float) -> None:
    """Prevent real delays during retry tests."""


def make_provider(handler):
    """Create an HTTP provider backed by a mock transport."""
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatProvider(
        "gemini",
        "https://test.example/v1",
        "test-key",
        "test-model",
        client=client,
    )
    return provider, client


def test_cost_inr_for_known_model():
    cost = cost_inr("gemini-3.8-flash", 1000, 2000, 95.0)
    assert cost == 0.78375


def test_unknown_model_cost_and_token_estimation():
    assert cost_inr("unknown-model", 100, 100, 95.0) == 0
    assert estimate_tokens("abcdefgh") == 2
    assert estimate_tokens("") == 1


def test_provider_body_includes_stream_options():
    client = httpx.AsyncClient()
    provider = OpenAICompatProvider(
        "gemini", "https://test.example/v1", "key", "model", client=client
    )

    normal = provider._body([{"role": "user", "content": "Hi"}], 0.2, False)
    streaming = provider._body([{"role": "user", "content": "Hi"}], 0.2, True)

    assert "stream" not in normal
    assert streaming["stream"] is True
    assert streaming["stream_options"]["include_usage"] is True


@pytest.mark.asyncio
async def test_provider_generate_maps_response_and_usage():
    async def handler(request):
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "pong"}}],
                "usage": {
                    "prompt_tokens": 8,
                    "completion_tokens": 1,
                },
            },
        )

    provider, client = make_provider(handler)
    try:
        reply = await provider.generate([{"role": "user", "content": "ping"}])
        assert reply.text == "pong"
        assert reply.tokens_in == 8
        assert reply.tokens_out == 1
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_provider_429_is_retryable_and_reads_retry_after():
    async def handler(request):
        return httpx.Response(
            429,
            headers={"retry-after": "2"},
            text="rate limited",
        )

    provider, client = make_provider(handler)
    try:
        with pytest.raises(LLMError) as caught:
            await provider.generate([])

        assert caught.value.retryable is True
        assert caught.value.retry_after == 2.0
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_provider_auth_error_and_timeout_are_not_retryable():
    async def auth_handler(request):
        return httpx.Response(401, text="unauthorized")

    provider, client = make_provider(auth_handler)
    try:
        with pytest.raises(LLMError) as caught:
            await provider.generate([])
        assert caught.value.retryable is False
    finally:
        await client.aclose()

    async def timeout_handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    provider, client = make_provider(timeout_handler)
    try:
        with pytest.raises(LLMError) as caught:
            await provider.generate([])
        assert caught.value.retryable is False
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_fake_llm_generate_uses_scripted_answer():
    fake = FakeLLM(script=["Hello Varshini"])

    reply = await fake.generate([])

    assert reply.text == "Hello Varshini"
    assert reply.tokens_in == 12
    assert reply.tokens_out == 2
    assert fake.calls == 1


@pytest.mark.asyncio
async def test_fake_llm_stream_returns_pieces_and_usage():
    fake = FakeLLM(script=["Hello world"])
    usage = type(
        "Usage",
        (),
        {
            "tokens_in": 0,
            "tokens_out": 0,
        },
    )()

    pieces = [piece async for piece in fake.stream([], usage)]

    assert pieces == ["Hello ", "world "]
    assert usage.tokens_in == 12
    assert usage.tokens_out == 2


def test_circuit_breaker_lifecycle():
    now = [0.0]
    breaker = CircuitBreaker(
        threshold=2,
        cooldown=30,
        clock=lambda: now[0],
    )

    assert breaker.state == "closed"
    assert breaker.allow() is True

    breaker.failure()
    breaker.failure()

    assert breaker.state == "open"
    assert breaker.allow() is False

    now[0] = 30.0
    assert breaker.state == "half-open"
    assert breaker.allow() is True

    breaker.success()
    assert breaker.state == "closed"
    assert breaker.failures == 0


@pytest.mark.asyncio
async def test_gateway_primary_success_records_call():
    records = []

    async def recorder(row):
        records.append(row)

    primary = FakeLLM(
        name="gemini",
        model="gemini-3.8-flash",
        script=["Hello"],
    )
    gateway = LLMGateway([primary], recorder=recorder)

    result = await gateway.generate(
        [{"role": "user", "content": "Hi"}],
        prompt_version="chat_system_v1",
    )

    assert result.text == "Hello"
    assert result.provider == "gemini"
    assert result.fallback_used is False
    assert len(records) == 1
    assert records[0]["status"] == "ok"
    assert records[0]["prompt_version"] == "chat_system_v1"


@pytest.mark.asyncio
async def test_gateway_retries_retryable_error():
    primary = FakeLLM(
        name="gemini",
        script=[
            LLMError("temporary", retryable=True),
            "Recovered",
        ],
    )
    gateway = LLMGateway(
        [primary],
        sleep=no_sleep,
        max_attempts=2,
    )

    result = await gateway.generate([])

    assert result.text == "Recovered"
    assert primary.calls == 2
    assert result.fallback_used is False


@pytest.mark.asyncio
async def test_gateway_does_not_retry_nonretryable_error():
    primary = FakeLLM(
        name="gemini",
        script=[LLMError("invalid key", retryable=False)],
    )
    fallback = FakeLLM(
        name="groq",
        script=["Fallback answer"],
    )
    gateway = LLMGateway(
        [primary, fallback],
        sleep=no_sleep,
    )

    result = await gateway.generate([])

    assert result.text == "Fallback answer"
    assert primary.calls == 1
    assert fallback.calls == 1
    assert result.fallback_used is True


@pytest.mark.asyncio
async def test_gateway_falls_back_after_primary_retries_exhausted():
    primary = FakeLLM(
        name="gemini",
        script=[
            LLMError("temporary 1", retryable=True),
            LLMError("temporary 2", retryable=True),
        ],
    )
    fallback = FakeLLM(name="groq", script=["Groq answer"])

    gateway = LLMGateway(
        [primary, fallback],
        sleep=no_sleep,
        max_attempts=2,
    )

    result = await gateway.generate([])

    assert result.text == "Groq answer"
    assert primary.calls == 2
    assert fallback.calls == 1
    assert result.fallback_used is True


@pytest.mark.asyncio
async def test_gateway_skips_open_circuit():
    primary = FakeLLM(name="gemini")
    fallback = FakeLLM(name="groq", script=["Backup"])

    gateway = LLMGateway(
        [primary, fallback],
        breaker_threshold=2,
    )

    breaker = gateway.breakers["gemini"]
    breaker.failure()
    breaker.failure()

    result = await gateway.generate([])

    assert result.text == "Backup"
    assert primary.calls == 0
    assert fallback.calls == 1


@pytest.mark.asyncio
async def test_gateway_without_providers_raises_unavailable():
    gateway = LLMGateway([])

    with pytest.raises(LLMUnavailable):
        await gateway.generate([])


@pytest.mark.asyncio
async def test_recorder_failure_does_not_break_answer():
    async def broken_recorder(row):
        raise RuntimeError("database unavailable")

    primary = FakeLLM(
        name="gemini",
        script=["Still answered"],
    )
    gateway = LLMGateway(
        [primary],
        recorder=broken_recorder,
    )

    result = await gateway.generate([])

    assert result.text == "Still answered"


@pytest.mark.asyncio
async def test_gateway_stream_returns_result_after_pieces():
    primary = FakeLLM(
        name="gemini",
        script=["Hello world"],
    )
    gateway = LLMGateway([primary])

    items = [item async for item in gateway.stream([])]

    assert items[:2] == ["Hello ", "world "]
    assert isinstance(items[-1], LLMResult)
    assert items[-1].text == "Hello world "


@pytest.mark.asyncio
async def test_stream_preserves_request_id_after_context_reset():
    recorded_calls = []

    async def recorder(row):
        recorded_calls.append(row)

    primary = FakeLLM(
        name="gemini",
        script=["Hello world"],
    )

    gateway = LLMGateway(
        [primary],
        recorder=recorder,
    )

    token = request_id_ctx.set("test-request-123")
    stream = gateway.stream([])

    try:
        first_piece = await anext(stream)
    finally:
        request_id_ctx.reset(token)

    remaining = [item async for item in stream]

    assert first_piece == "Hello "
    assert isinstance(remaining[-1], LLMResult)
    assert len(recorded_calls) == 1
    assert recorded_calls[0]["request_id"] == "test-request-123"


@pytest.mark.asyncio
async def test_stream_falls_back_before_first_piece():
    primary = FakeLLM(
        name="gemini",
        script=[LLMError("unavailable", retryable=True)],
    )
    fallback = FakeLLM(
        name="groq",
        script=["Backup answer"],
    )
    gateway = LLMGateway([primary, fallback])

    items = [item async for item in gateway.stream([])]

    assert items[0] == "Backup "
    assert items[1] == "answer "
    assert isinstance(items[-1], LLMResult)
    assert items[-1].fallback_used is True


@pytest.mark.asyncio
async def test_stream_does_not_fallback_after_partial_answer():
    primary = FakeLLM(
        name="gemini",
        script=[
            (
                "partial",
                LLMError("stream interrupted", retryable=True),
            )
        ],
    )
    fallback = FakeLLM(name="groq", script=["Must not be used"])
    gateway = LLMGateway([primary, fallback])

    pieces = []

    with pytest.raises(LLMUnavailable, match="failed mid-answer"):
        async for piece in gateway.stream([]):
            pieces.append(piece)

    assert pieces == ["Half ", "an ", "answer "]
    assert fallback.calls == 0
