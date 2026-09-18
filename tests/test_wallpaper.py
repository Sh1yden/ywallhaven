"""Tests for the Windows wallpaper service."""

import ctypes
import types
from io import BytesIO

import pytest
from PIL import Image as PILImage

from app.service import wallpaper


def _make_jpeg_bytes(width=800, height=600):
    """Build in-memory JPEG bytes (RGB, no files)."""
    image = PILImage.new("RGB", (width, height), (10, 20, 30))
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def _make_png_bytes(width=800, height=600):
    """Build in-memory PNG bytes (RGBA, no files)."""
    image = PILImage.new(
        "RGBA", (width, height), (10, 20, 30, 128)
    )
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _make_gif_bytes(width=100, height=100):
    """Build in-memory animated GIF bytes (2 frames)."""
    first = PILImage.new("RGB", (width, height), (255, 0, 0))
    second = PILImage.new("RGB", (width, height), (0, 0, 255))
    buffer = BytesIO()
    first.save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=[second],
        duration=100,
        loop=0,
    )
    return buffer.getvalue()


def _decode_size(data):
    """Return (width, height) of image bytes."""
    with PILImage.open(BytesIO(data)) as image:
        return image.size


def _patch_temp(monkeypatch, tmp_path):
    """Point wallpaper.temp_path at an isolated tmp file."""
    target = tmp_path / "ywallhaven-wallpaper.jpg"
    monkeypatch.setattr(wallpaper, "temp_path", lambda: target)
    return target


async def _direct_to_thread(func, *args, **kwargs):
    """Run to_thread target inline (no thread pool)."""
    return func(*args, **kwargs)


def _use_direct_to_thread(monkeypatch):
    """Replace asyncio.to_thread with a direct call."""
    monkeypatch.setattr(
        wallpaper.asyncio, "to_thread", _direct_to_thread
    )


def _stub_metrics(monkeypatch, width, height):
    """Stub windll.user32.GetSystemMetrics values."""
    seen = []

    def _metrics(index):
        seen.append(index)
        if index == 0:
            return width
        return height

    user32 = types.SimpleNamespace(GetSystemMetrics=_metrics)
    stub = types.SimpleNamespace(user32=user32)
    monkeypatch.setattr(ctypes, "windll", stub, raising=False)
    return seen


def _stub_spi(monkeypatch, result=None, exc=None, seen=None):
    """Stub windll.user32.SystemParametersInfoW."""
    def _spi(*args, **kwargs):
        if seen is not None:
            seen.append((args, kwargs))
        if exc is not None:
            raise exc
        return result

    user32 = types.SimpleNamespace(SystemParametersInfoW=_spi)
    stub = types.SimpleNamespace(user32=user32)
    monkeypatch.setattr(ctypes, "windll", stub, raising=False)
    return stub


# --- is_supported ---


def test_is_supported_on_windows(monkeypatch):
    """win32 platform reports wallpaper as supported."""
    monkeypatch.setattr(wallpaper.sys, "platform", "win32")
    assert wallpaper.is_supported() is True


def test_is_supported_on_linux(monkeypatch):
    """Linux platform reports wallpaper as unsupported."""
    monkeypatch.setattr(wallpaper.sys, "platform", "linux")
    assert wallpaper.is_supported() is False


def test_is_supported_on_darwin(monkeypatch):
    """macOS platform reports wallpaper as unsupported."""
    monkeypatch.setattr(wallpaper.sys, "platform", "darwin")
    assert wallpaper.is_supported() is False


# --- pick_or_resize ---


def test_pick_jpeg_match_returns_same_bytes():
    """Matching ratio JPEG/RGB returns input byte-for-byte."""
    data = _make_jpeg_bytes(1920, 1080)
    assert wallpaper.pick_or_resize(data, (1920, 1080)) == data


def test_pick_png_match_converts_to_jpeg():
    """Matching ratio PNG/RGBA returns JPEG (SOI marker)."""
    data = _make_png_bytes(1920, 1080)
    result = wallpaper.pick_or_resize(data, (1920, 1080))
    assert result is not None
    assert result[:2] == b"\xff\xd8"
    assert result != data


def test_pick_mismatch_downscales_to_screen():
    """Mismatched ratio downscales inside screen, JPEG out."""
    data = _make_jpeg_bytes(2000, 1000)
    result = wallpaper.pick_or_resize(data, (1920, 1080))
    assert result is not None
    assert result[:2] == b"\xff\xd8"
    width, height = _decode_size(result)
    assert width <= 1920
    assert height <= 1080


def test_pick_none_screen_jpeg_passthrough():
    """Unknown screen returns JPEG/RGB input unchanged."""
    data = _make_jpeg_bytes(800, 600)
    assert wallpaper.pick_or_resize(data, None) == data


def test_pick_none_screen_png_to_jpeg():
    """Unknown screen converts PNG input to JPEG."""
    data = _make_png_bytes(800, 600)
    result = wallpaper.pick_or_resize(data, None)
    assert result is not None
    assert result[:2] == b"\xff\xd8"


def test_pick_zero_screen_jpeg_passthrough():
    """Zero screen size acts like unknown (no resize)."""
    data = _make_jpeg_bytes(800, 600)
    assert wallpaper.pick_or_resize(data, (0, 0)) == data


def test_pick_invalid_screen_png_to_jpeg():
    """Negative screen size converts PNG without resize."""
    data = _make_png_bytes(800, 600)
    result = wallpaper.pick_or_resize(data, (-1, 5))
    assert result is not None
    assert result[:2] == b"\xff\xd8"


def test_pick_animated_gif_returns_none():
    """Animated GIF input is refused with None."""
    data = _make_gif_bytes()
    assert wallpaper.pick_or_resize(data, (1920, 1080)) is None
    assert wallpaper.pick_or_resize(data, None) is None


def test_pick_broken_bytes_returns_none():
    """Garbage input is refused with None (no raise)."""
    data = b"not-an-image"
    assert wallpaper.pick_or_resize(data, (1920, 1080)) is None
    assert wallpaper.pick_or_resize(data, None) is None


# --- write_temp / cleanup_temp ---


def test_write_temp_creates_and_overwrites(monkeypatch, tmp_path):
    """Temp file is written and overwritten on repeat."""
    target = _patch_temp(monkeypatch, tmp_path)
    first = wallpaper.write_temp(b"first-bytes")
    assert first == target
    assert target.read_bytes() == b"first-bytes"
    second = wallpaper.write_temp(b"second-bytes")
    assert second == target
    assert target.read_bytes() == b"second-bytes"


def test_cleanup_temp_removes_file(monkeypatch, tmp_path):
    """cleanup_temp deletes the temp file."""
    target = _patch_temp(monkeypatch, tmp_path)
    target.write_bytes(b"data")
    wallpaper.cleanup_temp()
    assert not target.exists()


def test_cleanup_temp_missing_file_ok(monkeypatch, tmp_path):
    """cleanup_temp without a file does not raise."""
    _patch_temp(monkeypatch, tmp_path)
    wallpaper.cleanup_temp()


# --- apply_wallpaper ---


def test_apply_unsupported_returns_false(monkeypatch, tmp_path):
    """Non-Windows never touches ctypes.windll."""
    monkeypatch.setattr(wallpaper, "is_supported", lambda: False)
    seen = []
    _stub_spi(monkeypatch, result=1, seen=seen)
    assert wallpaper.apply_wallpaper(tmp_path / "x.jpg") is False
    assert seen == []


def test_apply_success_returns_true(monkeypatch, tmp_path):
    """SystemParametersInfoW returning 1 means success."""
    monkeypatch.setattr(wallpaper, "is_supported", lambda: True)
    seen = []
    _stub_spi(monkeypatch, result=1, seen=seen)
    assert wallpaper.apply_wallpaper(tmp_path / "x.jpg") is True
    assert len(seen) == 1


def test_apply_zero_returns_false(monkeypatch, tmp_path):
    """SystemParametersInfoW returning 0 means failure."""
    monkeypatch.setattr(wallpaper, "is_supported", lambda: True)
    _stub_spi(monkeypatch, result=0)
    assert wallpaper.apply_wallpaper(tmp_path / "x.jpg") is False


def test_apply_exception_returns_false(monkeypatch, tmp_path):
    """Win32 errors are caught and reported as False."""
    monkeypatch.setattr(wallpaper, "is_supported", lambda: True)
    _stub_spi(monkeypatch, exc=OSError("boom"))
    assert wallpaper.apply_wallpaper(tmp_path / "x.jpg") is False


# --- set_wallpaper_from_url ---


@pytest.mark.asyncio
async def test_set_unsupported_platform(monkeypatch):
    """Non-Windows returns Windows-only without fetching."""
    monkeypatch.setattr(wallpaper, "is_supported", lambda: False)
    calls = []

    async def _fetch(url):
        calls.append(url)
        return b"data"

    ok, message = await wallpaper.set_wallpaper_from_url(
        _fetch, "https://example.com/w.jpg"
    )
    assert ok is False
    assert message == "Setting wallpaper is available on Windows only"
    assert calls == []


@pytest.mark.asyncio
async def test_set_fetch_none_fails(monkeypatch):
    """A None download reports a download failure."""
    monkeypatch.setattr(wallpaper, "is_supported", lambda: True)

    async def _fetch(url):
        return None

    ok, message = await wallpaper.set_wallpaper_from_url(
        _fetch, "https://example.com/w.jpg", screen=(1920, 1080)
    )
    assert ok is False
    assert message == "Failed to download wallpaper"


@pytest.mark.asyncio
async def test_set_fetch_raises_fails(monkeypatch):
    """A raising downloader reports a download failure."""
    monkeypatch.setattr(wallpaper, "is_supported", lambda: True)

    async def _fetch(url):
        raise RuntimeError("boom")

    ok, message = await wallpaper.set_wallpaper_from_url(
        _fetch, "https://example.com/w.jpg", screen=(1920, 1080)
    )
    assert ok is False
    assert message == "Failed to download wallpaper"


@pytest.mark.asyncio
async def test_set_animated_refused(monkeypatch):
    """Animated input maps to the animated message."""
    monkeypatch.setattr(wallpaper, "is_supported", lambda: True)
    _use_direct_to_thread(monkeypatch)
    monkeypatch.setattr(
        wallpaper, "pick_or_resize", lambda data, screen: None
    )
    monkeypatch.setattr(
        wallpaper, "_looks_animated", lambda data: True
    )

    async def _fetch(url):
        return b"fake-data"

    ok, message = await wallpaper.set_wallpaper_from_url(
        _fetch, "https://example.com/a.gif", screen=(1920, 1080)
    )
    assert ok is False
    assert message == "Animated images can't be set as wallpaper"


@pytest.mark.asyncio
async def test_set_prepare_failed(monkeypatch):
    """Non-animated prepare failure maps to prepare message."""
    monkeypatch.setattr(wallpaper, "is_supported", lambda: True)
    _use_direct_to_thread(monkeypatch)
    monkeypatch.setattr(
        wallpaper, "pick_or_resize", lambda data, screen: None
    )
    monkeypatch.setattr(
        wallpaper, "_looks_animated", lambda data: False
    )

    async def _fetch(url):
        return b"fake-data"

    ok, message = await wallpaper.set_wallpaper_from_url(
        _fetch, "https://example.com/w.jpg", screen=(1920, 1080)
    )
    assert ok is False
    assert message == "Failed to prepare wallpaper"


@pytest.mark.asyncio
async def test_set_write_failed(monkeypatch):
    """A None temp path maps to the save message."""
    monkeypatch.setattr(wallpaper, "is_supported", lambda: True)
    _use_direct_to_thread(monkeypatch)
    monkeypatch.setattr(
        wallpaper, "pick_or_resize", lambda data, screen: b"jpg"
    )
    monkeypatch.setattr(wallpaper, "write_temp", lambda data: None)

    async def _fetch(url):
        return b"fake-data"

    ok, message = await wallpaper.set_wallpaper_from_url(
        _fetch, "https://example.com/w.jpg", screen=(1920, 1080)
    )
    assert ok is False
    assert message == "Failed to save wallpaper file"


@pytest.mark.asyncio
async def test_set_apply_failed(monkeypatch, tmp_path):
    """A rejected apply maps to the set message."""
    monkeypatch.setattr(wallpaper, "is_supported", lambda: True)
    _use_direct_to_thread(monkeypatch)
    monkeypatch.setattr(
        wallpaper, "pick_or_resize", lambda data, screen: b"jpg"
    )
    _patch_temp(monkeypatch, tmp_path)
    monkeypatch.setattr(
        wallpaper, "apply_wallpaper", lambda path: False
    )

    async def _fetch(url):
        return b"fake-data"

    ok, message = await wallpaper.set_wallpaper_from_url(
        _fetch, "https://example.com/w.jpg", screen=(1920, 1080)
    )
    assert ok is False
    assert message == "Failed to set wallpaper"


@pytest.mark.asyncio
async def test_set_happy_path(monkeypatch, tmp_path):
    """Full pipeline writes the temp file and applies it."""
    monkeypatch.setattr(wallpaper, "is_supported", lambda: True)
    _use_direct_to_thread(monkeypatch)
    target = _patch_temp(monkeypatch, tmp_path)
    monkeypatch.setattr(
        wallpaper, "apply_wallpaper", lambda path: True
    )
    data = _make_jpeg_bytes(800, 600)

    async def _fetch(url):
        return data

    ok, message = await wallpaper.set_wallpaper_from_url(
        _fetch, "https://example.com/w.jpg", screen=(800, 600)
    )
    assert ok is True
    assert message == "Wallpaper set"
    assert target.exists()
    assert target.read_bytes() == data


# --- get_screen_size ---


def test_screen_size_unsupported(monkeypatch):
    """Non-Windows has no screen size."""
    monkeypatch.setattr(wallpaper, "is_supported", lambda: False)
    assert wallpaper.get_screen_size() is None


def test_screen_size_returns_metrics(monkeypatch):
    """Metrics 0/1 map to (1920, 1080)."""
    monkeypatch.setattr(wallpaper, "is_supported", lambda: True)
    _stub_metrics(monkeypatch, 1920, 1080)
    assert wallpaper.get_screen_size() == (1920, 1080)


def test_screen_size_windll_error(monkeypatch):
    """Win32 errors map to None (no raise)."""
    monkeypatch.setattr(wallpaper, "is_supported", lambda: True)

    def _boom(index):
        raise OSError("boom")

    user32 = types.SimpleNamespace(GetSystemMetrics=_boom)
    stub = types.SimpleNamespace(user32=user32)
    monkeypatch.setattr(ctypes, "windll", stub, raising=False)
    assert wallpaper.get_screen_size() is None


def test_screen_size_zero_returns_none(monkeypatch):
    """Zero metrics mean unavailable (None)."""
    monkeypatch.setattr(wallpaper, "is_supported", lambda: True)
    _stub_metrics(monkeypatch, 0, 0)
    assert wallpaper.get_screen_size() is None
