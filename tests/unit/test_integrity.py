import hashlib
import json

from nikshaynavigator.ingest.integrity import verify_corpus


def add_record(root, name, content):
    raw = root / "data" / "raw" / "ctd"
    raw.mkdir(parents=True, exist_ok=True)

    path = raw / name
    path.write_bytes(content)

    record = {
        "url": f"https://example.test/{name}",
        "path": path.relative_to(root).as_posix(),
        "status": "downloaded",
        "sha256": hashlib.sha256(content).hexdigest(),
    }

    manifest = root / "data" / "manifest.jsonl"
    manifest.parent.mkdir(parents=True, exist_ok=True)

    with manifest.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")

    return path


def test_integrity_passes_valid_corpus(tmp_path):
    add_record(tmp_path, "guide.pdf", b"valid guideline")

    result = verify_corpus(tmp_path)

    assert result["passed"] is True
    assert result["verified"] == 1


def test_integrity_detects_missing_file(tmp_path):
    path = add_record(tmp_path, "guide.pdf", b"valid guideline")
    path.unlink()

    result = verify_corpus(tmp_path)

    assert result["passed"] is False
    assert len(result["missing"]) == 1


def test_integrity_detects_modified_file(tmp_path):
    path = add_record(tmp_path, "guide.pdf", b"original document")
    path.write_bytes(b"modified document")

    result = verify_corpus(tmp_path)

    assert result["passed"] is False
    assert len(result["corrupted"]) == 1


def test_integrity_detects_partial_and_orphan_files(tmp_path):
    add_record(tmp_path, "guide.pdf", b"valid guideline")

    raw = tmp_path / "data" / "raw" / "ctd"
    (raw / "unfinished.pdf.part").write_bytes(b"partial")
    (raw / "unregistered.pdf").write_bytes(b"orphan")

    result = verify_corpus(tmp_path)

    assert result["passed"] is False
    assert len(result["partial_files"]) == 1
    assert len(result["orphan_files"]) == 1


def test_integrity_detects_duplicate_documents(tmp_path):
    content = b"same guideline content"

    add_record(tmp_path, "guide-a.pdf", content)
    add_record(tmp_path, "guide-b.pdf", content)

    result = verify_corpus(tmp_path)

    assert result["passed"] is True
    assert len(result["duplicates"]) == 1
    assert len(result["duplicates"][0]["paths"]) == 2


def test_integrity_rejects_unsafe_manifest_path(tmp_path):
    raw = tmp_path / "data"
    raw.mkdir()

    manifest = raw / "manifest.jsonl"
    manifest.write_text(
        json.dumps(
            {
                "url": "https://example.test/unsafe.pdf",
                "path": "../../outside.pdf",
                "status": "downloaded",
                "sha256": "abc",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = verify_corpus(tmp_path)

    assert result["passed"] is False
    assert len(result["unsafe_paths"]) == 1
