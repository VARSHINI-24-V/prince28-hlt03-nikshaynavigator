"""Submit and monitor a NikshayNavigator ingestion batch."""

import argparse
import asyncio
import json
import sys
from urllib.parse import urljoin

import httpx

from nikshaynavigator.config import get_settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Submit and monitor a document ingestion batch."
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base URL of the NikshayNavigator API.",
    )
    parser.add_argument(
        "--sha256",
        action="append",
        default=[],
        metavar="HASH",
        help="Explicit document SHA-256 hash. Repeat for multiple documents.",
    )
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--source", default="")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--max-wait-seconds", type=int, default=3600)
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    settings = get_settings()

    if not settings.admin_token:
        print("ERROR: ADMIN_TOKEN is not configured.", file=sys.stderr)
        return 1

    base_url = args.base_url.rstrip("/")
    headers = {"X-Admin-Token": settings.admin_token}

    request_data = {
        "limit": args.limit,
        "source": args.source,
        "retry_failed": args.retry_failed,
        "sha256s": args.sha256,
    }

    timeout = httpx.Timeout(30.0, connect=5.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(
                f"{base_url}/v1/ingest",
                json=request_data,
                headers=headers,
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            print(f"ERROR submitting ingestion request: {error}")
            return 1

        result = response.json()

        if response.status_code == 200 or not result.get("job_id"):
            print("No new ingestion job was created.")
            print(json.dumps(result, indent=2))
            return 0

        job_id = result["job_id"]
        status_url = urljoin(
            f"{base_url}/",
            result.get("status_url") or f"/v1/ingest/{job_id}",
        )

        print(f"Job ID: {job_id}")
        print(f"Initially queued: {result.get('queued', 0)}")
        print("Monitoring ingestion...\n")

        loop = asyncio.get_running_loop()
        deadline = loop.time() + args.max_wait_seconds

        while loop.time() < deadline:
            try:
                status_response = await client.get(
                    status_url,
                    headers=headers,
                )
                status_response.raise_for_status()
            except httpx.HTTPError as error:
                print(f"ERROR checking job status: {error}")
                return 1

            status = status_response.json()

            print(
                f"Queued: {status.get('queued', 0)} | "
                f"Running: {status.get('running', 0)} | "
                f"Done: {status.get('done', 0)} | "
                f"Skipped: {status.get('skipped', 0)} | "
                f"Failed: {status.get('failed', 0)} | "
                f"Pages: {status.get('pages', 0)}"
            )

            if status.get("finished", False):
                print("\nIngestion job finished.")
                return 1 if status.get("failed", 0) > 0 else 0

            await asyncio.sleep(args.poll_seconds)

        print("\nTimed out waiting for the job.")
        print(f"Check job status later using: {status_url}")
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
