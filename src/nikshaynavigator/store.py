import json
from pathlib import Path
from typing import Any

from nikshaynavigator.config import get_settings


def load_documents() -> list[dict[str, Any]]:
    """Load guideline records from the configured JSON file."""
    data_file: Path = get_settings().data_file

    if not data_file.exists():
        return []

    with data_file.open("r", encoding="utf-8") as file:
        records = json.load(file)

    if not isinstance(records, list):
        raise TypeError("Guideline data must be a JSON list.")

    return records
