"""Integrity verification for the NikshayNavigator document corpus."""

import hashlib
import json
from collections import defaultdict
from pathlib import Path


def sha256_file(path: Path) -> str:
    """Calculate a file's SHA-256 without loading it entirely into memory."""
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def verify_corpus(root: Path) -> dict:
    """Verify manifest records, file hashes, orphan files and partial files."""
    root = root.resolve()
    manifest_path = root / "data" / "manifest.jsonl"
    raw_dir = root / "data" / "raw"

    if not manifest_path.is_file():
        raise FileNotFoundError("data/manifest.jsonl was not found.")

    records_by_url = {}
    invalid_records = []

    for line_number, line in enumerate(
        manifest_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue

        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            invalid_records.append(f"Invalid JSON at line {line_number}")
            continue

        if not isinstance(record, dict) or not record.get("url"):
            invalid_records.append(f"Invalid record at line {line_number}")
            continue

        records_by_url[record["url"]] = record

    downloaded = [
        record
        for record in records_by_url.values()
        if record.get("status") == "downloaded"
    ]

    missing = []
    corrupted = []
    missing_hashes = []
    unsafe_paths = []
    verified = set()
    hash_groups = defaultdict(list)

    for record in downloaded:
        relative = Path(str(record.get("path", "")))
        path = (root / relative).resolve()

        if not path.is_relative_to(raw_dir.resolve()):
            unsafe_paths.append(str(relative))
            continue

        if not path.is_file():
            missing.append(str(relative))
            continue

        expected_hash = record.get("sha256")

        if not expected_hash:
            missing_hashes.append(str(relative))
            continue

        actual_hash = sha256_file(path)

        if actual_hash != expected_hash:
            corrupted.append(
                {
                    "path": str(relative),
                    "expected": expected_hash,
                    "actual": actual_hash,
                }
            )
            continue

        verified.add(path)
        hash_groups[actual_hash].append(str(relative))

    partial_files = []
    orphan_files = []

    if raw_dir.exists():
        for path in raw_dir.rglob("*"):
            if not path.is_file():
                continue

            if path.name.endswith(".part"):
                partial_files.append(str(path.relative_to(root)))
            elif path.resolve() not in verified:
                orphan_files.append(str(path.relative_to(root)))

    duplicates = [
        {
            "sha256": digest,
            "paths": paths,
        }
        for digest, paths in hash_groups.items()
        if len(paths) > 1
    ]

    passed = not any(
        [
            invalid_records,
            missing,
            corrupted,
            missing_hashes,
            unsafe_paths,
            partial_files,
            orphan_files,
        ]
    )

    return {
        "manifest_records": len(records_by_url),
        "downloaded_records": len(downloaded),
        "verified": len(verified),
        "missing": missing,
        "corrupted": corrupted,
        "missing_hashes": missing_hashes,
        "unsafe_paths": unsafe_paths,
        "partial_files": partial_files,
        "orphan_files": orphan_files,
        "duplicates": duplicates,
        "invalid_records": invalid_records,
        "passed": passed,
    }
