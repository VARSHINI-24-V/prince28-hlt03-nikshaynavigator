"""Question classification using versioned prompts and the LLM gateway."""

import re
from collections.abc import Iterable, Sequence
from typing import Literal, cast

from nikshaynavigator.llm.gateway import LLMGateway, Message
from nikshaynavigator.llm.prompts import load_prompt

Label = Literal["docs", "personal", "off_topic"]

VALID_LABELS = frozenset({"docs", "personal", "off_topic"})


def build_messages(question: str, system_prompt: str) -> list[Message]:
    """Build classifier messages with the question isolated in XML-style tags."""

    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question must be a non-empty string.")

    if not isinstance(system_prompt, str) or not system_prompt.strip():
        raise ValueError("System prompt must be a non-empty string.")

    # Prevent a question from injecting its own closing question tag.
    safe_question = re.sub(
        r"</?\s*question\s*>",
        lambda match: match.group(0).replace("<", "&lt;").replace(">", "&gt;"),
        question,
        flags=re.IGNORECASE,
    )

    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": f"<question>\n{safe_question}\n</question>",
        },
    ]


def parse_label(response: str) -> Label:
    """Accept exactly one valid lowercase classification label."""

    if not isinstance(response, str):
        raise TypeError("Classifier response must be a string.")

    label = response.strip()

    if label not in VALID_LABELS:
        raise ValueError(
            "Invalid classifier response. Expected exactly one of: "
            "docs, personal, off_topic."
        )

    return cast(Label, label)


async def classify(
    question: str,
    gateway: LLMGateway,
    prompt_version: str = "classify_v1",
) -> Label:
    """Classify one question using the selected versioned prompt."""

    if not question.strip():
        raise ValueError("Question must not be empty.")

    if not prompt_version.startswith("classify_v"):
        raise ValueError("Classifier requires a classify prompt version.")

    system_prompt = load_prompt(prompt_version)
    messages = build_messages(question, system_prompt)

    result = await gateway.generate(
        messages,
        purpose="classify",
        prompt_version=prompt_version,
        temperature=0.0,
    )

    return parse_label(result.text)


def accuracy(expected: Sequence[str], predicted: Sequence[str]) -> float:
    """Calculate classification accuracy as a fraction between 0 and 1."""

    if len(expected) != len(predicted):
        raise ValueError("Expected and predicted lists must have equal lengths.")

    if not expected:
        raise ValueError("Cannot calculate accuracy for an empty dataset.")

    invalid = (set(expected) | set(predicted)) - VALID_LABELS

    if invalid:
        raise ValueError(f"Unknown classification labels: {sorted(invalid)}")

    correct = sum(
        actual == target for target, actual in zip(expected, predicted, strict=True)
    )

    return correct / len(expected)


def find_leaks(prompt: str, questions: Iterable[str]) -> list[str]:
    """Find complete evaluation questions embedded in a prompt."""

    normalized_prompt = " ".join(prompt.split()).casefold()

    leaked_questions = []

    for question in questions:
        normalized_question = " ".join(question.split()).casefold()

        if normalized_question and normalized_question in normalized_prompt:
            leaked_questions.append(question)

    return leaked_questions
