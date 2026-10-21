"""Native Windows environment checks."""

import os
import sys

import pytest

import updater.main as helper_main
from app.service import wallpaper

pytestmark = [
    pytest.mark.native,
    pytest.mark.native_win,
    pytest.mark.skipif(
        sys.platform != "win32", reason="Windows-only native test"
    ),
]


def test_windows_environment():
    """The test really runs on Windows."""
    assert sys.platform == "win32"
    assert os.name == "nt"


def test_process_alive_for_current_process():
    """The Win32 probe sees the current process."""
    assert helper_main._process_alive(os.getpid()) is True


def test_screen_size_uses_win32_metrics():
    """The Windows backend reads the real screen metrics."""
    size = wallpaper._WindowsBackend().screen_size()
    if size is None:
        pytest.skip("no interactive desktop session")
    assert size[0] > 0
    assert size[1] > 0


def test_helper_replaces_and_restarts_windows(
    monkeypatch, tmp_path
):
    """The helper uses Windows restart flags after a real replace."""
    src = tmp_path / "new.exe"
    dst = tmp_path / "app.exe"
    src.write_bytes(b"new")
    dst.write_bytes(b"old")

    started: list = []
    monkeypatch.setattr(
        helper_main, "_process_alive", lambda pid: False
    )
    monkeypatch.setattr(
        helper_main.subprocess,
        "Popen",
        lambda cmd, **kwargs: started.append((cmd, kwargs)),
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
    assert started
    _cmd, kwargs = started[0]
    assert kwargs["creationflags"] == 0x00000008 | 0x00000200
    assert kwargs["close_fds"] is True
    assert "start_new_session" not in kwargs
