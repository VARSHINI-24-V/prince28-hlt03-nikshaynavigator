"""Strict metadata contract for NikshayNavigator documents."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Short = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
]

Values = Annotated[
    list[Short],
    Field(default_factory=list, max_length=8),
]

Summary = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=20, max_length=300),
]

Kind = Literal[
    "guideline",
    "rule",
    "notice",
    "list",
    "report",
    "faq",
    "form",
    "tutorial",
    "reference",
    "other",
]


class DocMeta(BaseModel):
    """Validated metadata record extracted from one source document."""

    model_config = ConfigDict(extra="forbid")

    # Common fields
    doc_kind: Kind
    year: int | None = Field(default=None, ge=1950, le=2027)
    language: Literal["en", "ta", "hi", "other"]
    summary: Summary
    topics: Annotated[
        list[Short],
        Field(min_length=1, max_length=6),
    ]

    # NikshayNavigator-specific fields
    document: Values
    topic: Values
    population: Values
    recommendation: Values
    supersedes: Values

    @field_validator("topics")
    @classmethod
    def normalize_topics(cls, value: list[str]) -> list[str]:
        """Normalize topic names and remove case-insensitive duplicates."""

        return list(dict.fromkeys(topic.lower() for topic in value))
