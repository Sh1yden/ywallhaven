"""Tests for the app entry-point helpers."""

import sys

from app import main


def test_cleanup_update_files_removes_leftovers(tmp_path, monkeypatch) -> None:
    import os
    import time

    leftover = tmp_path / "ywallhaven-0.7.2-update.exe"
    keep = tmp_path / "keep.exe"
    leftover.write_bytes(b"x")
    keep.write_bytes(b"x")
    # Make leftover old enough to be cleaned (our cleanup keeps fresh <600s)
    old = time.time() - 700
    os.utime(leftover, (old, old))

    monkeypatch.setattr(main, "gettempdir", lambda: str(tmp_path))
    main._cleanup_update_files()

    assert not leftover.exists()
    assert keep.exists()


def test_cleanup_update_files_ignores_oserror(tmp_path, monkeypatch) -> None:
    target = tmp_path / "ywallhaven-0.7.2-update.exe"
    target.mkdir()

    monkeypatch.setattr(main, "gettempdir", lambda: str(tmp_path))
    main._cleanup_update_files()


def test_cleanup_update_files_removes_appimage_leftovers(
    tmp_path, monkeypatch
) -> None:
    import os
    import time

    leftover = tmp_path / "ywallhaven-0.12.0-update.AppImage"
    leftover.write_bytes(b"x")
    old = time.time() - 700
    os.utime(leftover, (old, old))

    monkeypatch.setattr(main, "gettempdir", lambda: str(tmp_path))
    main._cleanup_update_files()

    assert not leftover.exists()


def test_trim_updater_log_removes_large_log(tmp_path, monkeypatch) -> None:
    exe = tmp_path / "ywallhaven.exe"
    exe.write_bytes(b"")
    monkeypatch.setattr(sys, "executable", str(exe))

    big = tmp_path / "ywallhaven_updater.log"
    big.write_bytes(b"x" * (main._UPDATER_LOG_LIMIT + 1))
    main._trim_updater_log()
    assert not big.exists()


def test_trim_updater_log_keeps_small_log(tmp_path, monkeypatch) -> None:
    exe = tmp_path / "ywallhaven.exe"
    exe.write_bytes(b"")
    monkeypatch.setattr(sys, "executable", str(exe))

    small = tmp_path / "ywallhaven_updater.log"
    small.write_bytes(b"tiny")
    main._trim_updater_log()
    assert small.exists()


def test_cleanup_never_raises(monkeypatch) -> None:
    def failing_cleanup() -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(main, "_cleanup_update_files", failing_cleanup)
    main.cleanup()


def test_cleanup_calls_wallpaper_cleanup_temp(monkeypatch) -> None:
    """Shutdown wires the wallpaper temp cleanup in."""
    called: list = []
    monkeypatch.setattr(
        "app.service.wallpaper.cleanup_temp",
        lambda: called.append(True),
    )
    monkeypatch.setattr(main, "_cleanup_update_files", lambda: None)
    main.cleanup()
    assert called == [True]