import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest

from nikshaynavigator.ingest import fetch as downloader


def test_slug_normalizes_names():
    assert downloader.slug("TB Guidelines 2025") == "tb-guidelines-2025"


def test_file_stem_is_stable():
    url = "https://example.test/guidelines/tb-2025.pdf"
    assert downloader.file_stem(url) == downloader.file_stem(url)


def test_pick_ext_from_url():
    assert (
        downloader.pick_ext("https://example.test/file.pdf", "application/octet-stream")
        == ".pdf"
    )


def test_pick_ext_from_content_type():
    assert (
        downloader.pick_ext("https://example.test/document", "application/pdf")
        == ".pdf"
    )


def test_backoff_delay_is_bounded(monkeypatch):
    calls = []

    def fake_uniform(low, high):
        calls.append((low, high))
        return high

    monkeypatch.setattr(downloader.random, "uniform", fake_uniform)

    delay = downloader.backoff_delay(3, base=1, cap=10)

    assert delay == 8
    assert calls == [(0, 8)]


def test_retry_after_seconds_and_http_date():
    assert downloader.retry_after_seconds("15") == 15

    future = datetime.now(UTC) + timedelta(seconds=60)
    value = format_datetime(future, usegmt=True)

    result = downloader.retry_after_seconds(value)

    assert result is not None
    assert 0 <= result <= 60


def test_read_sources_skips_comments_and_duplicates(tmp_path):
    csv_file = tmp_path / "sources.csv"

    csv_file.write_text(
        "# source notes\n"
        "url,source,licence,title\n"
        "https://example.test/a.pdf,ctd,Attribution,A\n"
        "https://example.test/a.pdf,ctd,Attribution,A\n",
        encoding="utf-8",
    )

    sources = downloader.read_sources(csv_file)

    assert len(sources) == 1
    assert sources[0].source == "ctd"


def test_read_sources_rejects_invalid_url(tmp_path):
    csv_file = tmp_path / "sources.csv"

    csv_file.write_text(
        "url,source,licence,title\nftp://example.test/a.pdf,ctd,Attribution,A\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="not an http"):
        downloader.read_sources(csv_file)


def test_read_sources_requires_licence(tmp_path):
    csv_file = tmp_path / "sources.csv"

    csv_file.write_text(
        "url,source,licence,title\nhttps://example.test/a.pdf,ctd,,A\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="licence"):
        downloader.read_sources(csv_file)


def test_manifest_add_and_done(tmp_path):
    manifest = downloader.Manifest(tmp_path / "data" / "manifest.jsonl")

    document = tmp_path / "data" / "raw" / "ctd" / "guide.pdf"
    document.parent.mkdir(parents=True)
    document.write_bytes(b"test PDF")

    record = {
        "url": "https://example.test/guide.pdf",
        "status": "downloaded",
        "path": "data/raw/ctd/guide.pdf",
    }

    manifest.add(record)

    assert manifest.done(record["url"], tmp_path)


def test_manifest_repairs_incomplete_last_line(tmp_path):
    path = tmp_path / "manifest.jsonl"

    valid = {
        "url": "https://example.test/a.pdf",
        "status": "failed",
    }

    path.write_text(
        json.dumps(valid) + "\n" + '{"url":',
        encoding="utf-8",
    )

    manifest = downloader.Manifest(path)

    assert valid["url"] in manifest.records
    assert path.read_text(encoding="utf-8").endswith("\n")


@pytest.mark.asyncio
async def test_robots_allows_permitted_path():
    async def handler(request):
        return httpx.Response(
            200,
            text="User-agent: examate-student-bot\nAllow: /public/\nDisallow: /private/\n",
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        robots = downloader.Robots(client)

        allowed, _delay = await robots.check("https://example.test/public/guide.pdf")

    assert allowed is True


@pytest.mark.asyncio
async def test_robots_blocks_disallowed_path():
    async def handler(request):
        return httpx.Response(
            200,
            text="User-agent: examate-student-bot\nDisallow: /private/\n",
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        robots = downloader.Robots(client)

        allowed, _ = await robots.check("https://example.test/private/guide.pdf")

    assert allowed is False


@pytest.mark.asyncio
async def test_robots_404_allows_unlisted_resources():
    async def handler(request):
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        robots = downloader.Robots(client)

        allowed, _ = await robots.check("https://example.test/guide.pdf")

    assert allowed is True


@pytest.mark.asyncio
async def test_robots_503_fails_closed():
    async def handler(request):
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        robots = downloader.Robots(client)

        allowed, _ = await robots.check("https://example.test/guide.pdf")

    assert allowed is False


@pytest.mark.asyncio
async def test_host_gate_enforces_delay(monkeypatch):
    clock = [100.0]
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(
        downloader.time,
        "monotonic",
        lambda: clock[0],
    )

    gate = downloader.HostGate(1.0, fake_sleep)

    await gate.wait("example.test")
    await gate.wait("example.test")

    assert sleeps == [1.0]


@pytest.mark.asyncio
async def test_download_writes_file_and_sha256(tmp_path):
    content = b"NikshayNavigator test document"

    async def handler(request):
        return httpx.Response(
            200,
            headers={"Content-Type": "application/pdf"},
            content=content,
        )

    source = downloader.Source(
        url="https://example.test/guide.pdf",
        source="ctd",
        licence="Attribution required",
        title="Test guideline",
    )

    raw_dir = tmp_path / "data" / "raw"

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await downloader._download(client, source, tmp_path, raw_dir)

    target = tmp_path / result["path"]

    assert target.read_bytes() == content
    assert result["sha256"] == hashlib.sha256(content).hexdigest()
    assert not target.with_name(target.name + ".part").exists()


@pytest.mark.asyncio
async def test_fetch_one_retries_temporary_503(tmp_path, monkeypatch):
    attempts = []

    async def handler(request):
        attempts.append(request.url.path)

        if len(attempts) == 1:
            return httpx.Response(503)

        return httpx.Response(
            200,
            headers={"Content-Type": "application/pdf"},
            content=b"Recovered document",
        )

    class AllowRobots:
        async def check(self, url):
            return True, 0.0

    async def fake_sleep(seconds):
        pass

    monkeypatch.setattr(
        downloader,
        "backoff_delay",
        lambda attempt: 0.0,
    )

    source = downloader.Source(
        "https://example.test/guide.pdf",
        "ctd",
        "Attribution required",
        "Guideline",
    )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await downloader.fetch_one(
            client,
            source,
            root=tmp_path,
            raw_dir=tmp_path / "data" / "raw",
            robots=AllowRobots(),
            gate=downloader.HostGate(0, fake_sleep),
            slots=asyncio.Semaphore(1),
            max_attempts=3,
            sleep=fake_sleep,
        )

    assert result["status"] == "downloaded"
    assert result["attempts"] == 2
    assert len(attempts) == 2


def test_manifest_resume_skips_completed_source(tmp_path):
    url = "https://example.test/guide.pdf"

    document = tmp_path / "data" / "raw" / "ctd" / "guide.pdf"
    document.parent.mkdir(parents=True)
    document.write_bytes(b"Previously downloaded")

    manifest = downloader.Manifest(tmp_path / "data" / "manifest.jsonl")

    manifest.add(
        {
            "url": url,
            "status": "downloaded",
            "path": "data/raw/ctd/guide.pdf",
        }
    )

    assert manifest.done(url, tmp_path)


@pytest.mark.asyncio
async def test_fetch_all_resumes_without_redownloading(tmp_path):
    source = downloader.Source(
        "https://example.test/guide.pdf",
        "ctd",
        "Attribution required",
        "Guideline",
    )

    document = tmp_path / "data" / "raw" / "ctd" / "guide.pdf"
    document.parent.mkdir(parents=True)
    document.write_bytes(b"Previously downloaded")

    manifest = downloader.Manifest(tmp_path / "data" / "manifest.jsonl")

    manifest.add(
        {
            "url": source.url,
            "status": "downloaded",
            "path": "data/raw/ctd/guide.pdf",
        }
    )

    counts = await downloader.fetch_all(
        [source],
        root=tmp_path,
    )

    assert counts["skipped"] == 1
    assert counts["downloaded"] == 0


@pytest.mark.asyncio
async def test_fetch_one_respects_retry_after(tmp_path, monkeypatch):
    attempts = 0
    sleeps = []

    async def handler(request):
        nonlocal attempts

        if request.url.path == "/robots.txt":
            return httpx.Response(
                200,
                text="User-agent: examate-student-bot\nAllow: /\n",
            )

        attempts += 1

        if attempts == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "3"},
            )

        return httpx.Response(
            200,
            headers={"Content-Type": "application/pdf"},
            content=b"Test guideline PDF",
        )

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(
        downloader,
        "backoff_delay",
        lambda attempt: 0.0,
    )

    source = downloader.Source(
        "https://example.test/guide.pdf",
        "ctd",
        "Attribution required",
        "Test guideline",
    )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await downloader.fetch_one(
            client,
            source,
            root=tmp_path,
            raw_dir=tmp_path / "data" / "raw",
            robots=downloader.Robots(client),
            gate=downloader.HostGate(0, fake_sleep),
            slots=asyncio.Semaphore(1),
            max_attempts=2,
            sleep=fake_sleep,
        )

    assert result["status"] == "downloaded"
    assert result["attempts"] == 2
    assert attempts == 2
    assert sleeps == [3.0]


@pytest.mark.asyncio
async def test_fetch_all_respects_max_concurrency(tmp_path):
    active = 0
    peak = 0

    async def handler(request):
        nonlocal active, peak

        if request.url.path == "/robots.txt":
            return httpx.Response(
                200,
                text="User-agent: examate-student-bot\nAllow: /\n",
            )

        active += 1
        peak = max(peak, active)

        await asyncio.sleep(0.02)

        active -= 1

        return httpx.Response(
            200,
            headers={"Content-Type": "application/pdf"},
            content=b"Test guideline",
        )

    sources = [
        downloader.Source(
            f"https://example.test/guide-{i}.pdf",
            "ctd",
            "Attribution required",
            f"Guideline {i}",
        )
        for i in range(8)
    ]

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        counts = await downloader.fetch_all(
            sources,
            root=tmp_path,
            max_concurrency=4,
            per_host_delay=0,
            max_attempts=1,
            client=client,
        )

    assert counts["downloaded"] == 8
    assert counts["failed"] == 0
    assert peak == 4


@pytest.mark.asyncio
async def test_download_cancellation_removes_partial_file(tmp_path):
    started = asyncio.Event()
    release = asyncio.Event()

    class SlowStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"%PDF-1.7 partial content"
            started.set()
            await release.wait()

        async def aclose(self):
            pass

    async def handler(request):
        return httpx.Response(
            200,
            headers={"Content-Type": "application/pdf"},
            stream=SlowStream(),
        )

    source = downloader.Source(
        "https://example.test/slow-guide.pdf",
        "ctd",
        "Attribution required",
        "Test guideline",
    )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        task = asyncio.create_task(
            downloader._download(
                client,
                source,
                tmp_path,
                tmp_path / "data" / "raw",
            )
        )

        await asyncio.wait_for(started.wait(), timeout=2)

        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    assert not list(tmp_path.rglob("*.part"))
    assert not list(tmp_path.rglob("*.pdf"))
