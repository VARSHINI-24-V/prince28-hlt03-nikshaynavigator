import pytest
from pydantic import ValidationError

from nikshaynavigator.llm.doc_meta import DocMeta

VALID_RECORD = {
    "doc_kind": "guideline",
    "year": 2025,
    "language": "en",
    "summary": "Official guidance for tuberculosis programme implementation.",
    "topics": ["Drug-resistant TB", "Treatment"],
    "document": ["DR-TB Management Guidelines"],
    "topic": ["Drug-resistant TB"],
    "population": ["Adults"],
    "recommendation": ["Follow the recommended treatment workflow"],
    "supersedes": [],
}


def test_valid_metadata_record():
    record = DocMeta.model_validate(VALID_RECORD)

    assert record.doc_kind == "guideline"
    assert record.year == 2025
    assert record.language == "en"


def test_extra_fields_are_forbidden():
    data = {**VALID_RECORD, "unknown_field": "unexpected"}

    with pytest.raises(ValidationError):
        DocMeta.model_validate(data)


@pytest.mark.parametrize(
    "kind",
    [
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
    ],
)
def test_supported_document_kinds(kind):
    data = {**VALID_RECORD, "doc_kind": kind}

    record = DocMeta.model_validate(data)

    assert record.doc_kind == kind


def test_invalid_document_kind_is_rejected():
    data = {**VALID_RECORD, "doc_kind": "circular"}

    with pytest.raises(ValidationError):
        DocMeta.model_validate(data)


@pytest.mark.parametrize("year", [None, 1950, 2027])
def test_valid_year_boundaries(year):
    data = {**VALID_RECORD, "year": year}

    record = DocMeta.model_validate(data)

    assert record.year == year


@pytest.mark.parametrize("year", [1949, 2028])
def test_year_outside_allowed_range_is_rejected(year):
    data = {**VALID_RECORD, "year": year}

    with pytest.raises(ValidationError):
        DocMeta.model_validate(data)


@pytest.mark.parametrize("language", ["en", "ta", "hi", "other"])
def test_supported_languages(language):
    data = {**VALID_RECORD, "language": language}

    record = DocMeta.model_validate(data)

    assert record.language == language


def test_invalid_language_is_rejected():
    data = {**VALID_RECORD, "language": "fr"}

    with pytest.raises(ValidationError):
        DocMeta.model_validate(data)


def test_topics_are_normalized_and_deduplicated():
    data = {
        **VALID_RECORD,
        "topics": [" TB ", "tb", "Treatment", "TREATMENT"],
    }

    record = DocMeta.model_validate(data)

    assert record.topics == ["tb", "treatment"]


def test_topics_cannot_be_empty():
    data = {**VALID_RECORD, "topics": []}

    with pytest.raises(ValidationError):
        DocMeta.model_validate(data)


def test_topics_cannot_exceed_six_items():
    data = {
        **VALID_RECORD,
        "topics": ["one", "two", "three", "four", "five", "six", "seven"],
    }

    with pytest.raises(ValidationError):
        DocMeta.model_validate(data)


def test_summary_must_contain_at_least_twenty_characters():
    data = {**VALID_RECORD, "summary": "Too short"}

    with pytest.raises(ValidationError):
        DocMeta.model_validate(data)


def test_summary_cannot_exceed_three_hundred_characters():
    data = {**VALID_RECORD, "summary": "x" * 301}

    with pytest.raises(ValidationError):
        DocMeta.model_validate(data)


def test_custom_fields_default_to_empty_lists():
    data = {
        key: value
        for key, value in VALID_RECORD.items()
        if key
        not in {
            "document",
            "topic",
            "population",
            "recommendation",
            "supersedes",
        }
    }

    record = DocMeta.model_validate(data)

    assert record.document == []
    assert record.topic == []
    assert record.population == []
    assert record.recommendation == []
    assert record.supersedes == []


def test_custom_list_cannot_exceed_eight_values():
    data = {
        **VALID_RECORD,
        "document": [f"Document {index}" for index in range(9)],
    }

    with pytest.raises(ValidationError):
        DocMeta.model_validate(data)


def test_custom_values_are_stripped():
    data = {**VALID_RECORD, "document": ["  NTEP Guideline  "]}

    record = DocMeta.model_validate(data)

    assert record.document == ["NTEP Guideline"]


def test_custom_value_cannot_exceed_eighty_characters():
    data = {**VALID_RECORD, "document": ["x" * 81]}

    with pytest.raises(ValidationError):
        DocMeta.model_validate(data)
