"""Load versioned prompts from the repository prompt directory."""

import re
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parents[3] / "prompts"

PROMPT_PATTERN = re.compile(r"^(?P<task>[a-z][a-z0-9_]*)_v(?P<version>[1-9]\d*)\.md$")

VERSION_PATTERN = re.compile(r"^[a-z][a-z0-9_]*_v[1-9]\d*$")


def find_prompts(task: str, prompt_dir: Path | None = None) -> list[str]:
    """Find available prompt versions for a task in numeric order."""

    if not re.fullmatch(r"[a-z][a-z0-9_]*", task):
        raise ValueError(f"Invalid prompt task: {task}")

    directory = prompt_dir or PROMPT_DIR

    if not directory.is_dir():
        return []

    matches = []

    for path in directory.glob(f"{task}_v*.md"):
        match = PROMPT_PATTERN.fullmatch(path.name)

        if match and match.group("task") == task:
            matches.append((int(match.group("version")), path))

    matches.sort(key=lambda item: item[0])

    return [f"{task}_v{version}" for version, _ in matches]


def load_prompt(
    prompt_version: str,
    prompt_dir: Path | None = None,
) -> str:
    """Load a prompt by its version identifier."""

    if not VERSION_PATTERN.fullmatch(prompt_version):
        raise ValueError(f"Invalid prompt version: {prompt_version}")

    directory = prompt_dir or PROMPT_DIR
    path = directory / f"{prompt_version}.md"

    if not path.is_file():
        raise FileNotFoundError(f"Prompt not found: {path}")

    content = path.read_text(encoding="utf-8-sig").strip()

    if not content:
        raise ValueError(f"Prompt is empty: {path}")

    return content
