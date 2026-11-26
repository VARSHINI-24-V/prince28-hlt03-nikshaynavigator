"""CLI for extracting and validating document metadata."""

import argparse
import asyncio
import time
from uuid import uuid4

from nikshaynavigator.config import get_settings
from nikshaynavigator.db.llm_calls import LlmCallRepository
from nikshaynavigator.db.session import make_engine, make_sessionmaker
from nikshaynavigator.llm.doc_meta import DocMeta
from nikshaynavigator.llm.extract import run
from nikshaynavigator.llm.gateway import build_gateway
from nikshaynavigator.llm.prompts import find_prompts, load_prompt


async def main(args: argparse.Namespace) -> None:
    """Run the metadata extraction pipeline."""

    versions = find_prompts("extract")

    if not versions:
        raise RuntimeError(
            "No extraction prompts found. Create prompts/extract_v1.md first."
        )

    version = versions[-1]
    prompt = load_prompt(version)

    settings = get_settings()
    engine = make_engine(settings)
    session_factory = make_sessionmaker(engine)

    async def record_llm_call(row: dict) -> None:
        """Persist LLM call usage and ensure each call has a request ID."""

        call = dict(row)
        call["request_id"] = call.get("request_id") or str(uuid4())

        async with session_factory() as session:
            await LlmCallRepository(session).record(call)

    gateway = build_gateway(
        settings,
        recorder=record_llm_call,
    )

    started = time.perf_counter()

    try:
        print(f"Prompt version: {version}")
        print(f"Maximum documents: {args.limit or 'all pending'}")
        print(f"Rate limit: {args.rpm} documents/minute")
        print(f"Text limit: {args.chars} characters/document")
        print(f"Retry failed: {args.retry_failed}")
        print()

        counts = await run(
            session_factory,
            gateway,
            DocMeta,
            prompt,
            version,
            limit=args.limit,
            rpm=args.rpm,
            chars=args.chars,
            retry_failed=args.retry_failed,
        )

        elapsed = time.perf_counter() - started
        processed = counts["ok"] + counts["failed"]

        cost = counts["cost_inr"]
        per_document = cost / processed if processed else 0.0

        print("\nMetadata extraction summary")
        print(f"Prompt: {version}")
        print(f"Pending: {counts['pending']}")
        print(f"Successful: {counts['ok']}")
        print(f"Repaired: {counts['repaired']}")
        print(f"Failed: {counts['failed']}")
        print(f"Tokens in: {counts['tokens_in']}")
        print(f"Tokens out: {counts['tokens_out']}")
        print(f"Estimated cost: Rs. {cost:.6f}")
        print(f"Average cost per processed document: Rs. {per_document:.6f}")
        print(f"Elapsed seconds: {elapsed:.1f}")

        if counts["stopped"]:
            print("Run stopped because the providers were unavailable.")
            print("Completed documents are saved. Rerun to resume.")

    finally:
        for provider in gateway.providers:
            client = getattr(provider, "_client", None)

            if client is not None:
                await client.aclose()

        await engine.dispose()


def cli() -> None:
    parser = argparse.ArgumentParser(
        description="Extract validated metadata from NikshayNavigator documents."
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum number of documents to process. Default: all pending.",
    )

    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry documents previously recorded as failed.",
    )

    parser.add_argument(
        "--rpm",
        type=float,
        default=12,
        help="Maximum documents processed per minute. Default: 12.",
    )

    parser.add_argument(
        "--chars",
        type=int,
        default=6000,
        help="Maximum source characters supplied to the model. Default: 6000.",
    )

    args = parser.parse_args()

    if args.limit < 0:
        parser.error("--limit cannot be negative.")

    if args.rpm <= 0:
        parser.error("--rpm must be greater than zero.")

    if args.chars < 1:
        parser.error("--chars must be at least 1.")

    asyncio.run(main(args))


if __name__ == "__main__":
    cli()
