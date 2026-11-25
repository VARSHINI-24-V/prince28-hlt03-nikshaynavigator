"""Send one direct HTTP request to each configured LLM provider."""

import asyncio
import time

import httpx

from nikshaynavigator.config import Settings


async def ping_provider(
    client: httpx.AsyncClient,
    name: str,
    base_url: str,
    api_key: str,
    model: str,
) -> bool:
    if not api_key:
        print(f"{name:<8} NO KEY")
        return False

    url = f"{base_url.rstrip('/')}/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with exactly: pong"}],
        "temperature": 0,
    }

    started = time.perf_counter()

    try:
        response = await client.post(
            url,
            headers=headers,
            json=payload,
        )

        latency_ms = int((time.perf_counter() - started) * 1000)

        if response.status_code != 200:
            print(
                f"{name:<8} FAILED HTTP {response.status_code}: {response.text[:250]}"
            )
            return False

        data = response.json()
        answer = data["choices"][0]["message"]["content"]
        usage = data.get("usage") or {}

        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)

        print(
            f"{name:<8} OK       {model} said '{answer}' "
            f"in {latency_ms} ms, "
            f"tokens in={tokens_in} out={tokens_out}"
        )
        return True

    except httpx.TimeoutException:
        print(f"{name:<8} FAILED: Request timed out")
        return False

    except httpx.HTTPError as exc:
        print(f"{name:<8} FAILED: {type(exc).__name__}")
        return False

    except (KeyError, IndexError, ValueError, TypeError):
        print(f"{name:<8} FAILED: Unexpected API response")
        return False


async def main() -> None:
    settings = Settings()

    async with httpx.AsyncClient(timeout=60.0) as client:
        await ping_provider(
            client,
            "gemini",
            settings.llm_primary_base_url,
            settings.gemini_api_key,
            settings.llm_primary_model,
        )

        await ping_provider(
            client,
            "groq",
            settings.llm_fallback_base_url,
            settings.groq_api_key,
            settings.llm_fallback_model,
        )


if __name__ == "__main__":
    asyncio.run(main())
