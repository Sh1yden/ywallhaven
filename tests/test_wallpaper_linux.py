"""Tests for the Linux wallpaper backend and dispatch."""

import subprocess
from pathlib import Path

import pytest

from app.service import wallpaper


def _force_linux(monkeypatch):
    monkeypatch.setattr(wallpaper.sys, "platform", "linux")


def test_select_backend_linux(monkeypatch):
    """Linux platform resolves to the Linux backend."""
    _force_linux(monkeypatch)
    backend = wallpaper._select_backend()
    assert backend.name == "linux"
    assert backend.supports is True


def test_select_backend_android_stub(monkeypatch):
    """Android resolves to an unsupported stub."""
    monkeypatch.setattr(wallpaper.sys, "platform", "android")
    backend = wallpaper._select_backend()
    assert backend.name == "android"
    assert backend.supports is False
    assert backend.apply(Path("/tmp/x.jpg")) is False


def test_linux_apply_no_tools_fails(monkeypatch, tmp_path):
    """Linux without helpers reports failure, no raise."""
    _force_linux(monkeypatch)
    monkeypatch.setattr(wallpaper.shutil, "which", lambda name: None)
    assert wallpaper.apply_wallpaper(tmp_path / "x.jpg") is False


def test_linux_apply_gsettings_success(monkeypatch, tmp_path):
    """GNOME path uses gsettings with a file:// URI."""
    _force_linux(monkeypatch)
    monkeypatch.setattr(
        wallpaper.shutil, "which", lambda name: "/usr/bin/" + name
    )
    calls = []

    def _ok(cmd, label):
        calls.append((cmd, label))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(wallpaper, "_run", _ok)
    target = tmp_path / "w.jpg"
    target.write_bytes(b"x")
    assert wallpaper.apply_wallpaper(target) is True
    assert calls
    assert calls[0][0][:3] == [
        "gsettings",
        "set",
        "org.gnome.desktop.background",
    ]
    assert calls[0][0][-1].startswith("file://")


def test_linux_apply_falls_through_to_feh(monkeypatch, tmp_path):
    """GNOME failure falls through to the feh fallback."""
    _force_linux(monkeypatch)

    def _which(name):
        if name in ("gsettings", "feh"):
            return "/usr/bin/" + name
        return None

    monkeypatch.setattr(wallpaper.shutil, "which", _which)
    calls = []

    def _run(cmd, label):
        calls.append(label)
        if label.startswith("gsettings"):
            return None
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(wallpaper, "_run", _run)
    target = tmp_path / "w.jpg"
    target.write_bytes(b"x")
    assert wallpaper.apply_wallpaper(target) is True
    assert any(label == "feh" for label in calls)


def test_linux_kde_prefers_plasma_apply(monkeypatch, tmp_path):
    """KDE sessions try plasma-apply-wallpaperimage first."""
    _force_linux(monkeypatch)
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    monkeypatch.setattr(
        wallpaper.shutil, "which", lambda name: "/usr/bin/" + name
    )
    calls = []

    def _ok(cmd, label):
        calls.append((cmd, label))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(wallpaper, "_run", _ok)
    target = tmp_path / "w.jpg"
    target.write_bytes(b"x")
    assert wallpaper.apply_wallpaper(target) is True
    assert calls[0][0][0].endswith("plasma-apply-wallpaperimage")


def test_run_tolerates_missing_binary(monkeypatch):
    """_run never raises on helper errors."""
    monkeypatch.setattr(
        wallpaper.subprocess,
        "run",
        lambda *a, **k: (_ for _ in ()).throw(OSError("boom")),
    )
    assert wallpaper._run(["feh", "x"], "feh") is None


def test_run_rejects_nonzero_exit(monkeypatch):
    """Non-zero exit codes map to None."""
    monkeypatch.setattr(
        wallpaper.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(
            ["x"], 1, "", "nope"
        ),
    )
    assert wallpaper._run(["x"], "x") is None


@pytest.mark.asyncio
async def test_set_linux_no_tool_message(monkeypatch, tmp_path):
    """Linux without helpers reports the no-tool message."""
    from io import BytesIO as _BytesIO

    from PIL import Image as _PILImage

    _force_linux(monkeypatch)
    target = tmp_path / "ywallhaven-wallpaper.jpg"
    monkeypatch.setattr(wallpaper, "temp_path", lambda: target)

    async def _inline_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(wallpaper.asyncio, "to_thread", _inline_to_thread)
    monkeypatch.setattr(wallpaper.shutil, "which", lambda name: None)

    image = _PILImage.new("RGB", (800, 600), (10, 20, 30))
    buffer = _BytesIO()
    image.save(buffer, format="JPEG")
    data = buffer.getvalue()

    async def _fetch(url):
        return data

    ok, message = await wallpaper.set_wallpaper_from_url(
        _fetch, "https://example.com/w.jpg", screen=(800, 600)
    )
    assert ok is False
    assert message == wallpaper._NO_TOOL_MESSAGE
