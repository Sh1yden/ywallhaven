"""Tests for the Linux wallpaper backend and dispatch."""

import subprocess

import pytest

from app.service import wallpaper


def _force_linux(monkeypatch):
    monkeypatch.setattr(wallpaper.sys, "platform", "linux")


def _force_plain_linux(monkeypatch):
    """Linux without the Noctalia shell (generic cascade)."""
    _force_linux(monkeypatch)
    monkeypatch.setattr(
        wallpaper, "_is_noctalia_session", lambda: False
    )


def test_select_backend_linux(monkeypatch):
    """Linux platform resolves to the Linux backend."""
    _force_plain_linux(monkeypatch)
    backend = wallpaper._select_backend()
    assert backend.name == "linux"
    assert backend.supports is True


def test_select_backend_android_stub(monkeypatch, tmp_path):
    """Android resolves to an unsupported stub."""
    monkeypatch.setattr(wallpaper.sys, "platform", "android")
    backend = wallpaper._select_backend()
    assert backend.name == "android"
    assert backend.supports is False
    assert backend.apply(tmp_path / "x.jpg") is False


def test_linux_apply_no_tools_fails(monkeypatch, tmp_path):
    """Linux without helpers reports failure, no raise."""
    _force_plain_linux(monkeypatch)
    monkeypatch.setattr(wallpaper.shutil, "which", lambda name: None)
    assert wallpaper.apply_wallpaper(tmp_path / "x.jpg") is False


def test_linux_apply_gsettings_success(monkeypatch, tmp_path):
    """GNOME path uses gsettings with a file:// URI."""
    _force_plain_linux(monkeypatch)
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
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
    _force_plain_linux(monkeypatch)

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
    _force_plain_linux(monkeypatch)
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


# --- Noctalia backend ---


def _force_noctalia(monkeypatch):
    """Linux with a live Noctalia shell (mocked detection)."""
    _force_linux(monkeypatch)
    monkeypatch.setattr(wallpaper, "_is_noctalia_session", lambda: True)


def test_select_backend_noctalia(monkeypatch):
    """Noctalia session resolves to the Noctalia backend."""
    _force_noctalia(monkeypatch)
    backend = wallpaper._select_backend()
    assert backend.name == "noctalia"
    assert backend.supports is True
    assert backend.wants_original is True


def test_noctalia_needs_binary_and_process(monkeypatch):
    """Missing binary never hijacks the cascade."""
    _force_linux(monkeypatch)
    monkeypatch.setattr(wallpaper.shutil, "which", lambda name: None)
    assert wallpaper._is_noctalia_session() is False
    assert wallpaper._select_backend().name == "linux"


def test_noctalia_apply_builds_ipc_command(monkeypatch, tmp_path):
    """Apply goes through wallpaper-set without a connector."""
    _force_noctalia(monkeypatch)
    calls = []

    def _ok(cmd, label):
        calls.append((cmd, label))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(wallpaper, "_run", _ok)
    target = tmp_path / "w.png"
    target.write_bytes(b"x")
    assert wallpaper.apply_wallpaper(target) is True
    assert calls == [
        (
            ["noctalia", "msg", "wallpaper-set", str(target.resolve())],
            "noctalia",
        )
    ]


def test_noctalia_apply_failure_message(monkeypatch, tmp_path):
    """Rejected IPC maps to the Noctalia failure message."""
    _force_noctalia(monkeypatch)
    monkeypatch.setattr(wallpaper, "_run", lambda cmd, label: None)
    target = tmp_path / "w.png"
    target.write_bytes(b"x")
    assert wallpaper.apply_wallpaper(target) is False
    assert wallpaper._select_backend().fail_message.startswith(
        "Failed to set wallpaper"
    )


@pytest.mark.asyncio
async def test_set_noctalia_keeps_original_bytes(monkeypatch, tmp_path):
    """Noctalia backend stores the untouched original file."""
    from io import BytesIO as _BytesIO

    from PIL import Image as _PILImage

    _force_noctalia(monkeypatch)
    target = tmp_path / "ywallhaven-wallpaper.jpg"
    monkeypatch.setattr(wallpaper, "temp_path", lambda: target)

    async def _inline_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(wallpaper.asyncio, "to_thread", _inline_to_thread)
    seen = []
    monkeypatch.setattr(
        wallpaper, "apply_wallpaper", lambda path: seen.append(path) or True
    )

    image = _PILImage.new("RGBA", (64, 64), (10, 20, 30, 128))
    buffer = _BytesIO()
    image.save(buffer, format="PNG")
    data = buffer.getvalue()

    async def _fetch(url):
        return data

    ok, message = await wallpaper.set_wallpaper_from_url(
        _fetch, "https://example.com/w.png", screen=(1920, 1080)
    )
    assert ok is True
    assert message == "Wallpaper set"
    assert target.read_bytes() == data
    assert seen == [target]


def test_plan_skips_gsettings_on_wayland(monkeypatch, tmp_path):
    """gsettings never runs on Wayland without GNOME (false success)."""
    _force_plain_linux(monkeypatch)
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-1")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "Hyprland")
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)

    backend = wallpaper._LinuxBackend()
    labels = [
        label for label, _ in backend._plan(tmp_path / "w.jpg", "hyprland")
    ]
    assert "gsettings" not in labels


def test_plan_keeps_gsettings_on_x11(monkeypatch, tmp_path):
    """X11 keeps gsettings as a last resort."""
    _force_plain_linux(monkeypatch)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "")

    backend = wallpaper._LinuxBackend()
    labels = [
        label for label, _ in backend._plan(tmp_path / "w.jpg", "")
    ]
    assert labels[-1] == "gsettings"


@pytest.mark.asyncio
async def test_set_linux_no_tool_message(monkeypatch, tmp_path):
    """Linux without helpers reports the no-tool message."""
    from io import BytesIO as _BytesIO

    from PIL import Image as _PILImage

    _force_plain_linux(monkeypatch)
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
