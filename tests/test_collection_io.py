"""Tests for collection download helpers and the slideshow engine."""

import asyncio
import zipfile

import pytest

from app.service.collection_io import (
    build_zip,
    display_name,
    resolve_bytes,
    unique_name,
)
from app.service.slideshow import SlideshowService, clamp_interval


def _wallpaper(wid="w1", path="https://example.com/w1.jpg"):
    return {"id": wid, "path": path, "thumbs": {"small": path}}


def test_unique_name_suffixes():
    taken: set = set()
    assert unique_name(taken, "w.jpg") == "w.jpg"
    assert unique_name(taken, "w.jpg") == "w(1).jpg"
    assert unique_name(taken, "w.jpg") == "w(2).jpg"


def test_display_name_remote_and_local():
    assert display_name(_wallpaper(), 0) == "w1.jpg"
    assert display_name({"path": "/pics/a.png"}, 3) == "a.png"
    assert display_name({}, 3) == "wallpaper-3.jpg"


@pytest.mark.asyncio
async def test_resolve_bytes_remote():
    async def _fetch(url):
        return b"data" if url == "https://example.com/w1.jpg" else None

    assert await resolve_bytes(_wallpaper(), _fetch) == b"data"
    assert await resolve_bytes(_wallpaper("x", ""), _fetch) is None

    async def _boom(url):
        raise RuntimeError("boom")

    assert await resolve_bytes(_wallpaper(), _boom) is None


@pytest.mark.asyncio
async def test_resolve_bytes_local(tmp_path):
    target = tmp_path / "a.jpg"
    target.write_bytes(b"local")

    async def _fetch(url):
        raise AssertionError("must not fetch local files")

    assert await resolve_bytes({"path": str(target)}, _fetch) == b"local"
    assert (
        await resolve_bytes({"path": str(tmp_path / "gone.jpg")}, _fetch)
        is None
    )


@pytest.mark.asyncio
async def test_build_zip_packs_and_reports(tmp_path):
    target = tmp_path / "a.jpg"
    target.write_bytes(b"local")

    async def _fetch(url):
        return {"https://example.com/w1.jpg": b"one"}.get(url)

    seen: list = []
    data, failed = await build_zip(
        [
            _wallpaper(),
            {"id": "l1", "path": str(target)},
            _wallpaper("bad", "https://example.com/missing.jpg"),
        ],
        _fetch,
        progress=lambda done, total: seen.append((done, total)),
    )

    assert data is not None
    assert failed == ["bad"]
    assert seen == [(1, 3), (2, 3), (3, 3)]
    with zipfile.ZipFile(__import__("io").BytesIO(data)) as archive:
        assert sorted(archive.namelist()) == ["a.jpg", "w1.jpg"]


@pytest.mark.asyncio
async def test_build_zip_all_failed_returns_none():
    async def _fetch(url):
        return None

    data, failed = await build_zip([_wallpaper()], _fetch)
    assert data is None
    assert failed == ["w1"]


def test_clamp_interval():
    assert clamp_interval(60) == 60
    assert clamp_interval(5) == 10
    assert clamp_interval("bad") == 300
    assert clamp_interval(None) == 300


@pytest.mark.asyncio
async def test_slideshow_sequential_cycles():
    applied: list = []

    async def _apply(wallpaper):
        applied.append(wallpaper["id"])
        return True

    engine = SlideshowService(_apply)
    assert await engine.start(
        [_wallpaper("a"), _wallpaper("b")],
        label="t",
        interval=3600,
        order="sequential",
    ) is True
    assert engine.active is True
    await engine.stop()
    assert engine.active is False


def test_pick_cycles_sequentially():
    walls = [_wallpaper("a"), _wallpaper("b")]
    item, pos = SlideshowService._pick(walls, 0, "sequential")
    assert (item["id"], pos) == ("a", 1)
    item, pos = SlideshowService._pick(walls, pos, "sequential")
    assert (item["id"], pos) == ("b", 2)
    item, pos = SlideshowService._pick(walls, pos, "sequential")
    assert (item["id"], pos) == ("a", 3)


def test_pick_random_stays_in_set():
    walls = [_wallpaper("a"), _wallpaper("b")]
    for _ in range(20):
        item, pos = SlideshowService._pick(walls, 0, "random")
        assert item["id"] in ("a", "b")
        assert pos == 0


@pytest.mark.asyncio
async def test_slideshow_empty_rejected():
    async def _apply(wallpaper):
        raise AssertionError("must not apply")

    engine = SlideshowService(_apply)
    assert await engine.start([], label="t", interval=10) is False
    assert engine.active is False


@pytest.mark.asyncio
async def test_slideshow_skips_failures_and_paused():
    applied: list = []

    async def _apply(wallpaper):
        if wallpaper["id"] == "bad":
            return False
        applied.append(wallpaper["id"])
        return True

    engine = SlideshowService(_apply)
    await engine.start([_wallpaper("bad")], label="t", interval=3600)
    # The first tick runs promptly and is skipped without killing.
    for _ in range(200):
        if engine.active:
            await asyncio.sleep(0.01)
            break
    await asyncio.sleep(0.05)
    assert engine.active is True
    await engine.stop()

    paused_engine = SlideshowService(_apply, paused=lambda: True)
    await paused_engine.start(
        [_wallpaper("ok")], label="t", interval=3600
    )
    await asyncio.sleep(0.05)
    await paused_engine.stop()
    assert applied == []


@pytest.mark.asyncio
async def test_slideshow_restart_replaces():
    applied: list = []

    async def _apply(wallpaper):
        applied.append(wallpaper["id"])
        return True

    engine = SlideshowService(_apply)
    await engine.start([_wallpaper("a")], label="one", interval=3600)
    await engine.start([_wallpaper("b")], label="two", interval=3600)
    assert engine.label == "two"
    await engine.stop()
