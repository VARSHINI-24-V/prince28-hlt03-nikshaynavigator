"""NikshayNavigator corpus fetch CLI.

Commands:
    uv run python scripts/fetch.py urls
    uv run python scripts/fetch.py repo OWNER/REPO --path docs ...
    uv run python scripts/fetch.py sitemap URL --include /guidelines/ ...
    uv run python scripts/fetch.py manual data/raw/ctd --from-url URL ...
"""

import argparse
import asyncio
import csv
import hashlib
import mimetypes
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlsplit

from nikshaynavigator.ingest.fetch import (
    Manifest,
    Robots,
    fetch_all,
    make_client,
    read_sources,
    slug,
)

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
MANIFEST_PATH = ROOT / "data" / "manifest.jsonl"
SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".html",
    ".htm",
    ".md",
    ".mdx",
    ".rst",
    ".adoc",
    ".yml",
    ".yaml",
    ".json",
    ".txt",
}


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def digest_file(path: Path) -> tuple[str, int]:
    """Calculate SHA-256 and size without loading the whole file."""
    digest = hashlib.sha256()
    size = 0

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)

    return digest.hexdigest(), size


def command_urls(args: argparse.Namespace) -> int:
    """Door 1: download URLs from the source CSV."""
    sources_path = ROOT / args.sources

    if not sources_path.is_file():
        raise FileNotFoundError(f"Source CSV not found: {sources_path}")

    sources = read_sources(sources_path)

    if not sources:
        raise ValueError("No valid sources found in the CSV.")

    print(f"Starting URL downloads for {len(sources)} sources...")

    number = 0

    def report(record: dict) -> None:
        nonlocal number
        number += 1

        status = record["status"]
        path = record.get("path", record.get("error", ""))

        print(f"[{number:4}] {status:<12} {record.get('bytes', 0):>10,} bytes  {path}")

    counts = asyncio.run(
        fetch_all(
            sources,
            root=ROOT,
            max_concurrency=args.max_concurrency,
            per_host_delay=args.delay,
            max_attempts=args.max_attempts,
            on_result=report,
        )
    )

    print("\nDownload summary")
    print(f"sources={len(sources)}")
    print(
        f"downloaded={counts['downloaded']} "
        f"skipped={counts['skipped']} "
        f"blocked={counts['blocked']} "
        f"failed={counts['failed']}"
    )

    return 1 if counts["failed"] else 0


def run_git(command: list[str], *, cwd: Path = ROOT) -> str:
    """Run Git and return its output, reporting useful errors."""
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode:
        raise RuntimeError(f"Git command failed:\n{result.stderr.strip()}")

    return result.stdout.strip()


def command_repo(args: argparse.Namespace) -> int:
    """Door 2: collect selected files from a Git repository."""
    if "/" not in args.repository:
        raise ValueError("Repository must be OWNER/REPO.")

    extensions = {
        ext.lower() if ext.startswith(".") else f".{ext.lower()}"
        for ext in (
            args.ext or [".md", ".mdx", ".rst", ".adoc", ".yml", ".json", ".txt"]
        )
    }

    with tempfile.TemporaryDirectory(prefix="nikshay-repo-") as temporary:
        clone_dir = Path(temporary) / "repository"

        command = [
            "git",
            "clone",
            "--depth",
            "1",
            "--filter=blob:none",
            "--sparse",
        ]

        if args.ref:
            command.extend(["--branch", args.ref])

        command.extend(
            [
                f"https://github.com/{args.repository}.git",
                str(clone_dir),
            ]
        )

        run_git(command)

        selected_path = Path(args.path)

        if selected_path.is_absolute() or ".." in selected_path.parts:
            raise ValueError("--path must be a safe repository-relative path.")

        run_git(
            [
                "git",
                "sparse-checkout",
                "set",
                "--",
                selected_path.as_posix(),
            ],
            cwd=clone_dir,
        )

        commit = run_git(
            ["git", "rev-parse", "HEAD"],
            cwd=clone_dir,
        )
        folder = clone_dir / selected_path

        if not folder.is_dir():
            raise FileNotFoundError(f"Repository folder does not exist: {args.path}")

        manifest = Manifest(MANIFEST_PATH)
        added = 0
        unchanged = 0
        destination = RAW_DIR / slug(args.source)

        for file_path in sorted(folder.rglob("*")):
            if (
                not file_path.is_file()
                or file_path.is_symlink()
                or file_path.suffix.lower() not in extensions
            ):
                continue

            relative = file_path.relative_to(clone_dir)
            relative_url = quote(relative.as_posix(), safe="/")
            source_url = (
                f"https://github.com/{args.repository}/blob/{commit}/{relative_url}"
            )

            if manifest.done(source_url, ROOT):
                unchanged += 1
                continue

            target = destination / relative.relative_to(selected_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, target)

            sha, size = digest_file(target)

            manifest.add(
                {
                    "url": source_url,
                    "source_url": source_url,
                    "source": args.source,
                    "licence": args.licence,
                    "title": relative.as_posix(),
                    "path": target.relative_to(ROOT).as_posix(),
                    "bytes": size,
                    "sha256": sha,
                    "content_type": mimetypes.guess_type(target.name)[0],
                    "status": "downloaded",
                    "attempts": 1,
                    "via": "git",
                    "commit": commit,
                    "fetched_at": now_iso(),
                }
            )

            added += 1

        print(
            f"repo={args.repository} commit={commit[:12]} "
            f"added={added} unchanged={unchanged}"
        )

    return 0


async def collect_sitemap_urls(
    sitemap_url: str,
    client,
    robots: Robots,
    visited: set[str],
    depth: int = 0,
) -> list[str]:
    """Read a sitemap or sitemap index, checking robots before each request."""
    if sitemap_url in visited:
        return []

    if depth > 3:
        raise ValueError("Sitemap nesting exceeds the supported depth.")

    visited.add(sitemap_url)

    allowed, _ = await robots.check(sitemap_url)

    if not allowed:
        print(f"Blocked sitemap by robots.txt: {sitemap_url}")
        return []

    response = await client.get(sitemap_url)
    response.raise_for_status()

    root = ET.fromstring(response.content)

    locations = [
        element.text.strip()
        for element in root.iter()
        if element.tag.endswith("loc") and element.text
    ]

    if root.tag.endswith("sitemapindex"):
        discovered: list[str] = []

        for nested_url in locations:
            discovered.extend(
                await collect_sitemap_urls(
                    nested_url, client, robots, visited, depth + 1
                )
            )

        return discovered

    return locations


async def command_sitemap_async(args: argparse.Namespace) -> int:
    """Discover candidate document URLs without downloading them."""
    client = make_client(max_concurrency=2)
    robots = Robots(client)

    try:
        urls = await collect_sitemap_urls(
            args.sitemap_url,
            client,
            robots,
            set(),
        )
    finally:
        await client.aclose()

    matches = [
        url
        for url in urls
        if all(part in url for part in args.include)
        and not any(part in url for part in args.exclude)
    ]

    matches = list(dict.fromkeys(matches))[: args.limit]

    if not matches:
        print("No matching sitemap URLs found.")
        return 0

    csv_path = ROOT / args.sources
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    existing: set[str] = set()

    if csv_path.exists():
        existing = {source.url for source in read_sources(csv_path)}
    else:
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["url", "source", "licence", "title"])

    added = 0

    with csv_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)

        for url in matches:
            if url in existing:
                continue

            filename = Path(urlsplit(url).path).name
            writer.writerow(
                [
                    url,
                    args.source,
                    args.licence,
                    filename or "Discovered document",
                ]
            )
            existing.add(url)
            added += 1

    print(f"sitemap_urls={len(urls)} matched={len(matches)} added_to_sources={added}")

    return 0


def command_sitemap(args: argparse.Namespace) -> int:
    return asyncio.run(command_sitemap_async(args))


def command_manual(args: argparse.Namespace) -> int:
    """Door 4: register files downloaded manually in a browser."""
    folder = (ROOT / args.directory).resolve()
    raw_root = RAW_DIR.resolve()

    if not folder.is_dir():
        raise FileNotFoundError(f"Manual download folder not found: {folder}")

    try:
        folder.relative_to(raw_root)
    except ValueError as error:
        raise ValueError(
            "Manual downloads must be inside the project's data/raw/ folder."
        ) from error

    manifest = Manifest(MANIFEST_PATH)
    destination = RAW_DIR / slug(args.source)
    added = 0

    for file_path in sorted(folder.rglob("*")):
        if (
            not file_path.is_file()
            or file_path.is_symlink()
            or file_path.name.endswith(".part")
        ):
            continue

        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        relative = file_path.relative_to(folder)
        target = destination / relative

        if file_path.resolve() != target.resolve():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, target)

        synthetic_url = (
            f"{args.from_url.rstrip('/')}#manual={quote(relative.as_posix(), safe='/')}"
        )

        if manifest.done(synthetic_url, ROOT):
            continue

        sha, size = digest_file(target)

        manifest.add(
            {
                "url": synthetic_url,
                "source_url": args.from_url,
                "source": args.source,
                "licence": args.licence,
                "title": target.name,
                "path": target.relative_to(ROOT).as_posix(),
                "bytes": size,
                "sha256": sha,
                "content_type": mimetypes.guess_type(target.name)[0],
                "status": "downloaded",
                "attempts": 1,
                "via": "manual",
                "fetched_at": now_iso(),
            }
        )

        added += 1

    print(f"folder={folder} added={added}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="NikshayNavigator polite, resumable corpus fetcher."
    )

    commands = parser.add_subparsers(dest="command", required=True)

    urls = commands.add_parser("urls", help="Download from data/sources.csv")
    urls.add_argument("--sources", default="data/sources.csv")
    urls.add_argument("--delay", type=float, default=0.5)
    urls.add_argument("--max-concurrency", type=int, default=4)
    urls.add_argument("--max-attempts", type=int, default=4)
    urls.set_defaults(func=command_urls)

    repo = commands.add_parser("repo", help="Collect files from a Git repository")
    repo.add_argument("repository", help="OWNER/REPO")
    repo.add_argument("--path", required=True)
    repo.add_argument("--ext", action="append")
    repo.add_argument("--ref")
    repo.add_argument("--source", required=True)
    repo.add_argument("--licence", required=True)
    repo.set_defaults(func=command_repo)

    sitemap = commands.add_parser("sitemap", help="Discover document URLs")
    sitemap.add_argument("sitemap_url")
    sitemap.add_argument("--include", action="append", default=[])
    sitemap.add_argument("--exclude", action="append", default=[])
    sitemap.add_argument("--limit", type=int, default=300)
    sitemap.add_argument("--source", required=True)
    sitemap.add_argument("--licence", required=True)
    sitemap.add_argument("--sources", default="data/sources.csv")
    sitemap.set_defaults(func=command_sitemap)

    manual = commands.add_parser("manual", help="Register browser-downloaded files")
    manual.add_argument("directory")
    manual.add_argument("--from-url", required=True)
    manual.add_argument("--source", required=True)
    manual.add_argument("--licence", required=True)
    manual.set_defaults(func=command_manual)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        return args.func(args)
    except (OSError, ValueError, RuntimeError, ET.ParseError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
