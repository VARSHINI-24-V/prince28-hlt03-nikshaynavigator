"""Week 1 self-check for NikshayNavigator.

Run:
    uv run python scripts/check_week1.py

With an explicit production URL:
    uv run python scripts/check_week1.py https://nikshaynavigator.onrender.com

This script checks project files, Git, tests and the live health endpoint.
It reads the project and does not modify files.
"""

import json
import re
import subprocess
import sys
import tomllib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

OK, BAD, WARN = "  ok ", "  ✗  ", "  ! "
results: list[tuple[str, bool]] = []


def check(
    day: str,
    label: str,
    passed: bool,
    hint: str = "",
    warn_only: bool = False,
) -> None:
    mark = OK if passed else (WARN if warn_only else BAD)
    print(f"{mark}{label}" + ("" if passed or not hint else f"\n       → {hint}"))

    if not warn_only:
        results.append((day, passed))


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=ROOT,
            check=False,
        )
    except FileNotFoundError as error:
        return subprocess.CompletedProcess(cmd, 127, "", str(error))


def exists(path: str) -> bool:
    return (ROOT / path).exists()


def main() -> int:
    live = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else None

    if not exists("pyproject.toml"):
        print("Run this script from your NikshayNavigator project.")
        return 2

    try:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        print(f"Could not read pyproject.toml: {error}")
        return 2

    if pyproject.get("project", {}).get("name") != "nikshaynavigator":
        print("Unexpected project name in pyproject.toml.")
        return 2

    readme = (
        (ROOT / "README.md").read_text(encoding="utf-8") if exists("README.md") else ""
    )
    notes = (
        (ROOT / "NOTES.md").read_text(encoding="utf-8") if exists("NOTES.md") else ""
    )

    tracked_result = run(["git", "ls-files"])
    tracked = tracked_result.stdout.splitlines()

    print("\nD01 · Repository, documentation and quality gates")

    for path in [
        "README.md",
        "docs/QUESTIONS.md",
        "docs/REQUIREMENTS.md",
        ".pre-commit-config.yaml",
        ".env.example",
        "uv.lock",
    ]:
        check("D01", path, exists(path), f"Missing: {path}")

    questions = (
        (ROOT / "docs/QUESTIONS.md").read_text(encoding="utf-8")
        if exists("docs/QUESTIONS.md")
        else ""
    )

    question_count = len(re.findall(r"^\s*##\s*Q\d+\.", questions, flags=re.MULTILINE))

    check(
        "D01",
        f"QUESTIONS.md has 10 questions ({question_count} found)",
        question_count >= 10,
        "Add evaluation questions until there are 10.",
    )

    todo_count = questions.count("TODO")
    check(
        "D01",
        "No TODO left in QUESTIONS.md",
        todo_count == 0,
        f"{todo_count} TODO markers remain.",
        warn_only=True,
    )

    check(
        "D01",
        ".env is NOT committed",
        tracked_result.returncode == 0 and ".env" not in tracked,
        "Run git rm --cached .env if it was accidentally tracked.",
    )

    check(
        "D01",
        "Pre-commit hooks installed",
        exists(".git/hooks/pre-commit"),
        "Run uv run pre-commit install.",
    )

    print("\nD02 · FastAPI service and sample data")

    for path in [
        "src/nikshaynavigator/main.py",
        "src/nikshaynavigator/config.py",
        "data/sample_records.json",
    ]:
        check("D02", path, exists(path), f"Missing: {path}")

    try:
        records = json.loads(
            (ROOT / "data/sample_records.json").read_text(encoding="utf-8")
        )
        record_count = len(records) if isinstance(records, list) else 0
    except (OSError, ValueError):
        record_count = 0

    check(
        "D02",
        f"Sample data has 20 records ({record_count} found)",
        record_count >= 20,
        "Add valid sample records to data/sample_records.json.",
    )

    print("\nD03 · PostgreSQL and migrations")

    migrations = (
        list((ROOT / "migrations/versions").glob("*.py"))
        if exists("migrations/versions")
        else []
    )

    check(
        "D03",
        f"Two or more migrations ({len(migrations)} found)",
        len(migrations) >= 2,
        "Check migrations/versions.",
    )

    for path in [
        "src/nikshaynavigator/db/models.py",
        "scripts/load_db.py",
    ]:
        check("D03", path, exists(path), f"Missing: {path}")

    check(
        "D03",
        "NOTES.md has Day 3 section",
        bool(re.search(r"^# Day 3\b", notes, flags=re.MULTILINE)),
        "Document PostgreSQL migrations and loader verification.",
    )

    print("\nD04 · Docker, Compose and tests")

    for path in [
        "Dockerfile",
        ".dockerignore",
        "docker-compose.yml",
        "Makefile",
        "tests/unit",
        "tests/integration",
    ]:
        check("D04", path, exists(path), f"Missing: {path}")

    check(
        "D04",
        "README has 'Run locally in one command'",
        "Run locally in one command" in readme,
        "Add the required local-run README section.",
    )

    tests = run(["uv", "run", "pytest", "tests/unit"])
    test_output = tests.stdout + tests.stderr
    summary = re.search(
        r"\d+ (?:passed|failed|error)[^\n]*",
        test_output,
    )
    test_summary = summary.group(0) if summary else "no test summary"

    check(
        "D04",
        f"Unit tests pass ({test_summary})",
        tests.returncode == 0,
        "Run uv run pytest tests/unit -v and fix the first failure.",
    )

    print("\nD05 · CI/CD and production")

    for path in [
        ".github/workflows/ci.yml",
        ".github/workflows/cd.yml",
        "scripts/smoke.py",
    ]:
        check("D05", path, exists(path), f"Missing: {path}")

    check(
        "D05",
        "README has CI badge",
        "actions/workflows/ci.yml/badge.svg" in readme,
        "Add the GitHub Actions CI badge.",
    )

    url_match = re.search(
        r"https://[\w.-]+\.onrender\.com",
        readme,
    )

    check(
        "D05",
        "README has live Render URL",
        bool(url_match),
        "Add the live Render URL to README.",
    )

    tags = run(["git", "tag", "--list", "week-1"]).stdout.strip()

    check(
        "D05",
        "week-1 Git tag exists",
        tags == "week-1",
        "Run git tag week-1 after completing Week 1.",
    )

    check(
        "D05",
        "NOTES.md has Day 5 section",
        bool(re.search(r"^# Day 5\b", notes, flags=re.MULTILINE)),
        "Document CI/CD, deployment and rollback.",
    )

    if live or url_match:
        base = live or url_match.group(0)
        print(f"\nLIVE · {base}")

        try:
            request = urllib.request.Request(
                f"{base}/health",
                headers={"Accept": "application/json"},
            )

            with urllib.request.urlopen(request, timeout=90) as response:
                body = json.loads(response.read().decode("utf-8"))

            if not isinstance(body, dict):
                raise TypeError("Health endpoint did not return a JSON object.")

            check(
                "LIVE",
                f"/health → 200, version {str(body.get('version'))[:7]}",
                True,
            )

            head = run(["git", "rev-parse", "--verify", "--quiet", "origin/main"])

            if head.returncode == 0:
                sha = head.stdout.strip()

                check(
                    "LIVE",
                    "Live version = latest origin/main",
                    body.get("version") == sha,
                    f"origin/main is {sha[:7]}. Check the latest CD deployment.",
                    warn_only=True,
                )

        except (OSError, json.JSONDecodeError, UnicodeDecodeError, TypeError) as error:
            check(
                "LIVE",
                "/health → 200",
                False,
                f"{error}. Check Render logs.",
            )

    total = len(results)
    passed = sum(ok for _, ok in results)

    print(f"\n{passed} of {total} checks passed.")

    for day in ["D01", "D02", "D03", "D04", "D05", "LIVE"]:
        missing = [d for d, ok in results if d == day and not ok]

        if missing:
            print(
                f"Start with {day}: {len(missing)} open item(s). "
                "Earlier days come first."
            )
            break
    else:
        print("Week 1 checks are complete. 🚀")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
