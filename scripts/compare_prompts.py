"""Benchmark classifier prompt versions against the evaluation dataset."""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from nikshaynavigator.config import get_settings
from nikshaynavigator.llm.classify import (
    VALID_LABELS,
    build_messages,
    find_leaks,
    parse_label,
)
from nikshaynavigator.llm.gateway import LLMUnavailable, build_gateway
from nikshaynavigator.llm.prompts import find_prompts, load_prompt

ROOT = Path(__file__).resolve().parents[1]
TESTSET = ROOT / "eval" / "prompt_testset.jsonl"
CACHE_DIR = ROOT / "eval" / "cache"


def digest(value: str) -> str:
    """Return a stable SHA-256 digest."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_testset() -> list[dict[str, str]]:
    """Load and validate the JSONL evaluation dataset."""

    if not TESTSET.is_file():
        raise FileNotFoundError(f"Evaluation dataset not found: {TESTSET}")

    questions = []

    for line_number, line in enumerate(
        TESTSET.read_text(encoding="utf-8-sig").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue

        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON on dataset line {line_number}") from exc

        if set(item) != {"question", "label"}:
            raise ValueError(
                f"Line {line_number} must contain only question and label."
            )

        if not isinstance(item["question"], str) or not item["question"].strip():
            raise ValueError(f"Question is empty on line {line_number}.")

        if item["label"] not in VALID_LABELS:
            raise ValueError(f"Invalid label on line {line_number}.")

        questions.append(item)

    if len(questions) != 20:
        raise ValueError(f"Expected exactly 20 questions, found {len(questions)}.")

    return questions


def load_cache(path: Path, prompt_hash: str) -> dict[str, dict]:
    """Load completed results that belong to the current prompt version."""

    cached = {}

    if not path.exists():
        return cached

    for line_number, line in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue

        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid JSON in cache {path}, line {line_number}."
            ) from exc

        if (
            record.get("status") == "completed"
            and record.get("prompt_hash") == prompt_hash
        ):
            cached[record["question_hash"]] = record

    return cached


def append_cache(path: Path, record: dict) -> None:
    """Append each completed result immediately for safe resumption."""

    with path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")
        file.flush()


async def run_benchmark(limit: int | None = None) -> None:
    """Run and compare all available classifier prompt versions."""

    questions = load_testset()

    if limit is not None:
        if limit < 1:
            raise ValueError("--limit must be at least 1.")
        questions = questions[:limit]

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    versions = find_prompts("classify")

    if not versions:
        raise RuntimeError("No classifier prompt versions were found.")

    for version in versions:
        print(f"Checking leakage for {version}...")
        prompt = load_prompt(version)
        leaks = find_leaks(
            prompt,
            [item["question"] for item in load_testset()],
        )

        if leaks:
            raise RuntimeError(
                f"{version} contains {len(leaks)} evaluation question leak(s)."
            )

        print("  Leakage check: PASS")

    gateway = build_gateway(get_settings())

    try:
        for version in versions:
            print(f"\n=== Benchmark: {version} ===")

            prompt = load_prompt(version)
            prompt_hash = digest(prompt)
            cache_path = CACHE_DIR / f"{version}.jsonl"

            cached = load_cache(cache_path, prompt_hash)
            cache_hits = 0

            for index, item in enumerate(questions, start=1):
                question = item["question"]
                expected = item["label"]
                question_hash = digest(question.strip())

                if question_hash in cached:
                    cache_hits += 1
                    print(f"[{index}/{len(questions)}] CACHED: {expected}")
                    continue

                messages = build_messages(question, prompt)

                try:
                    result = await gateway.generate(
                        messages,
                        purpose="classify",
                        prompt_version=version,
                        temperature=0.0,
                    )
                except LLMUnavailable as exc:
                    print(f"[{index}/{len(questions)}] PROVIDER ERROR: {exc}")
                    print("  Not cached; rerunning will retry this question.")
                    continue

                try:
                    predicted = parse_label(result.text)
                    parse_error = None
                except ValueError as exc:
                    predicted = None
                    parse_error = str(exc)

                record = {
                    "status": "completed",
                    "prompt_version": version,
                    "prompt_hash": prompt_hash,
                    "question_hash": question_hash,
                    "question": question,
                    "expected": expected,
                    "predicted": predicted,
                    "raw_response": result.text,
                    "parse_error": parse_error,
                    "provider": result.provider,
                    "model": result.model,
                    "latency_ms": result.latency_ms,
                    "tokens_in": result.tokens_in,
                    "tokens_out": result.tokens_out,
                    "fallback_used": result.fallback_used,
                    "cost_inr": result.cost_inr,
                }

                append_cache(cache_path, record)
                cached[question_hash] = record

                print(
                    f"[{index}/{len(questions)}] "
                    f"{expected} -> {predicted or 'INVALID'} "
                    f"({result.provider}, {result.latency_ms} ms)"
                )

            completed = [
                cached[digest(item["question"].strip())]
                for item in questions
                if digest(item["question"].strip()) in cached
            ]

            if completed:
                expected_labels = [item["expected"] for item in completed]
                predicted_labels = [
                    item["predicted"]
                    if item["predicted"] in VALID_LABELS
                    else "__invalid__"
                    for item in completed
                ]

                correct = sum(
                    expected == predicted
                    for expected, predicted in zip(
                        expected_labels,
                        predicted_labels,
                        strict=True,
                    )
                )

                score = correct / len(completed) * 100

                latencies = [item["latency_ms"] for item in completed]

                total_cost = sum(item["cost_inr"] for item in completed)

                invalid = sum(
                    item["predicted"] not in VALID_LABELS for item in completed
                )

                print(f"\n{version} RESULTS")
                print(f"Accuracy: {score:.1f}% ({correct}/{len(completed)} completed)")
                print(f"Coverage: {len(completed)}/{len(questions)}")
                print(f"Invalid outputs: {invalid}")
                print(f"Average latency: {sum(latencies) / len(latencies):.0f} ms")
                print(f"Estimated total cost: Rs. {total_cost:.6f}")
                print(f"Cache hits this run: {cache_hits}")
            else:
                print("No completed responses yet.")

    finally:
        for provider in gateway.providers:
            client = getattr(provider, "_client", None)
            if client is not None:
                await client.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare versioned NikshayNavigator classifier prompts."
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Run only the first N questions per prompt version.",
    )

    args = parser.parse_args()
    asyncio.run(run_benchmark(args.limit))


if __name__ == "__main__":
    main()
