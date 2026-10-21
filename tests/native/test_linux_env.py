"""Native Linux environment checks."""

import os
import sys
from pathlib import Path

import pytest

import updater.main as helper_main
from app.service import wallpaper

pytestmark = [
    pytest.mark.native,
    pytest.mark.native_linux,
    pytest.mark.skipif(
        sys.platform != "linux", reason="Linux-only native test"
    ),
]


def test_linux_environment():
    """The test really runs on Linux."""
    assert sys.platform == "linux"
    assert os.name == "posix"


def test_process_alive_for_current_process():
    """The POSIX probe sees the current process."""
    assert helper_main._process_alive(os.getpid()) is True


def test_process_running_sees_self():
    """The /proc scanner finds the current process by its comm name."""
    comm = Path("/proc/self/comm").read_text(
        encoding="utf-8"
    ).strip()
    assert wallpaper._process_running(comm) is True
    assert wallpaper._process_running("no-such-process-xyz") is False


def test_restart_posix_detaches_and_chmod(monkeypatch, tmp_path):
    """POSIX restart marks the target executable and detaches."""
    dst = tmp_path / "YWallhaven.AppImage"
    dst.write_bytes(b"app")
    dst.chmod(0o644)

    started: list = []
    monkeypatch.setattr(
        helper_main.subprocess,
        "Popen",
        lambda cmd, **kwargs: started.append((cmd, kwargs)),
    )
    logger = helper_main._setup_logger(
        type("Args", (), {"log": tmp_path / "h.log"})()
    )

    helper_main._restart(dst, logger)

    assert dst.stat().st_mode & 0o111
    assert started
    _cmd, kwargs = started[0]
    assert kwargs.get("start_new_session") is True
    assert "creationflags" not in kwargs


def test_helper_main_replaces_and_restarts_posix(
    monkeypatch, tmp_path
):
    """The helper replaces the file and preserves the exec bit."""
    src = tmp_path / "new.AppImage"
    dst = tmp_path / "YWallhaven.AppImage"
    src.write_bytes(b"new")
    src.chmod(0o644)
    dst.write_bytes(b"old")

    started: list = []
    monkeypatch.setattr(
        helper_main.subprocess,
        "Popen",
        lambda cmd, **kwargs: started.append(cmd),
    )
    monkeypatch.setattr(
        helper_main, "_process_alive", lambda pid: False
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "updater",
            "--pid", "1",
            "--src", str(src),
            "--dst", str(dst),
            "--log", str(tmp_path / "updater.log"),
            "--restart",
        ],
    )

    assert helper_main.main() == 0
    assert dst.read_bytes() == b"new"
    assert dst.stat().st_mode & 0o111
    assert started
