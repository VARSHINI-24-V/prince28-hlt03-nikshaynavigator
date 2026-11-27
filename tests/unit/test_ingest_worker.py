import pytest

from nikshaynavigator.workers.ingest import (
    Pace,
    Permanent,
    get_file,
    plan,
)


def make_record(
    sha: str,
    *,
    source: str = "ctd",
    status: str = "downloaded",
) -> dict:
    return {
        "sha256": sha * 64,
        "source": source,
        "status": status,
        "path": f"data/raw/{sha}.pdf",
        "url": f"https://example.com/{sha}.pdf",
        "licence": "Government publication",
        "title": f"Document {sha}",
    }


def test_plan_filters_downloaded_and_already_known_documents():
    records = [
        make_record("a"),
        make_record("b"),
        make_record("c", status="failed"),
        make_record("d", source="other"),
    ]

    result = plan(records, {"a" * 64}, source="ctd")

    assert len(result) == 1
    assert result[0]["sha256"] == "b" * 64


def test_plan_removes_duplicate_hashes_and_respects_limit():
    records = [
        make_record("a"),
        make_record("b"),
        make_record("a"),
        make_record("c"),
    ]

    result = plan(records, set(), limit=2)

    assert len(result) == 2
    assert [item["sha256"] for item in result] == [
        "a" * 64,
        "b" * 64,
    ]


@pytest.mark.asyncio
async def test_pace_waits_between_model_calls():
    current_time = [0.0]
    waits = []

    async def fake_sleep(seconds):
        waits.append(seconds)
        current_time[0] += seconds

    pace = Pace(
        12,
        clock=lambda: current_time[0],
        sleep=fake_sleep,
    )

    await pace.wait()
    await pace.wait()

    assert waits == [5.0]


@pytest.mark.asyncio
async def test_get_file_uses_existing_local_file(tmp_path):
    local_file = tmp_path / "guideline.pdf"
    local_file.write_bytes(b"sample PDF content")

    record = {
        "path": str(local_file),
        "via": "http",
    }

    result = await get_file(record, tmp_path, None)

    assert result == local_file
    assert result.read_bytes() == b"sample PDF content"


@pytest.mark.asyncio
async def test_get_file_rejects_missing_manual_file(tmp_path):
    record = {
        "path": str(tmp_path / "missing.pdf"),
        "via": "manual",
    }

    with pytest.raises(Permanent, match="exists only on the laptop"):
        await get_file(record, tmp_path, None)
