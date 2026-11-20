"""Smoke-test the live NikshayNavigator deployment."""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any


class SmokeTestError(Exception):
    """Raised when a production smoke check fails."""


def get_json(base_url: str, path: str) -> dict[str, Any]:
    """Make an HTTP GET request and return its JSON response."""
    request = urllib.request.Request(
        f"{base_url}{path}",
        headers={"Accept": "application/json"},
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status != 200:
                raise SmokeTestError(f"{path} returned HTTP {response.status}")

            data = json.loads(response.read().decode("utf-8"))

    except urllib.error.HTTPError as exc:
        raise SmokeTestError(f"{path} returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise SmokeTestError(f"{path} request failed: {exc.reason}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SmokeTestError(f"{path} returned invalid JSON") from exc

    if not isinstance(data, dict):
        raise SmokeTestError(f"{path} did not return a JSON object")

    return data


def run_smoke_test(base_url: str, expected_version: str | None) -> bool:
    """Check health, readiness, and document retrieval."""
    health = get_json(base_url, "/health")

    if health.get("status") != "ok":
        raise SmokeTestError("/health status is not 'ok'")

    version = health.get("version")

    if not isinstance(version, str) or not version:
        raise SmokeTestError("/health did not return a valid version")

    if health.get("env") != "production":
        raise SmokeTestError("/health environment is not production")

    if expected_version and version != expected_version:
        raise SmokeTestError(
            f"/health reports version {version}, waiting for {expected_version}"
        )

    print(f"ok   /health -> 200, version {version}")

    readiness = get_json(base_url, "/ready")

    if (
        readiness.get("status") != "ready"
        or readiness.get("checks", {}).get("database") is not True
    ):
        raise SmokeTestError("/ready reports that the database is not ready")

    print(f"ok   /ready -> 200 {readiness}")

    documents = get_json(base_url, "/v1/documents?limit=1")

    items = documents.get("items")
    total = documents.get("total")

    if not isinstance(items, list) or not isinstance(total, int):
        raise SmokeTestError(
            "/v1/documents did not return the expected response structure"
        )

    print(f"ok   /v1/documents?limit=1 -> 200 (total={total}, returned={len(items)})")

    return True


def main() -> int:
    """Parse arguments and retry smoke tests during deployment."""
    parser = argparse.ArgumentParser(
        description="Smoke-test a live NikshayNavigator deployment."
    )
    parser.add_argument("url", help="Production base URL")
    parser.add_argument(
        "--expect-version",
        default=None,
        help="Expected Git commit SHA reported by /health",
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=30,
        help="Maximum attempts (default: 30)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=10,
        help="Seconds between attempts (default: 10)",
    )

    args = parser.parse_args()

    if args.attempts < 1 or args.interval < 0:
        parser.error("--attempts must be positive and --interval non-negative")

    base_url = args.url.rstrip("/")

    if not base_url.startswith(("https://", "http://")):
        parser.error("URL must start with http:// or https://")

    for attempt in range(1, args.attempts + 1):
        try:
            run_smoke_test(base_url, args.expect_version)
            print("\nSmoke test passed")
            return 0
        except SmokeTestError as exc:
            print(f"waiting: attempt {attempt}/{args.attempts}: {exc}")

            if attempt < args.attempts:
                time.sleep(args.interval)

    print("\nSmoke test failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
