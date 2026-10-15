"""Tests for the AppDir stager (no PyInstaller needed)."""

import os
import stat
import sys

sys.path.insert(0, "scripts")

from make_appdir import build_appdir, validate_desktop


def _fake_dist(tmp_path):
    """Create a minimal fake Linux build output with a PNG icon."""
    dist = tmp_path / "dist"
    folder = dist / "ywallhaven"
    folder.mkdir(parents=True)
    binary = folder / "ywallhaven"
    binary.write_bytes(b"elf-main")
    (folder / "_internal").mkdir()
    (folder / "_internal" / "lib.txt").write_text("lib")
    helper = dist / "ywallhaven-updater"
    helper.write_bytes(b"elf-helper")
    icon = tmp_path / "icon.png"
    # Minimal valid 1x1 PNG.
    icon.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452"
            "000000010000000108060000001f15c4"
            "890000000d4944415478d76360000000"
            "020001e221bc330000000049454e44ae"
            "426082"
        )
    )
    return dist, icon


def test_build_appdir_layout(tmp_path):
    """AppDir gets AppRun, desktop, icon, main and helper."""
    dist, icon = _fake_dist(tmp_path)

    result = build_appdir(dist=dist, icon_png=icon)

    appdir = result["appdir"]
    assert (appdir / "AppRun").is_file()
    assert os.access(appdir / "AppRun", os.X_OK)
    assert result["desktop"].read_text(
        encoding="utf-8"
    ).startswith("[Desktop Entry]")
    assert result["icon"].is_file()
    assert result["main"].read_bytes() == b"elf-main"
    assert result["helper"].read_bytes() == b"elf-helper"
    assert (appdir / "usr" / "bin" / "ywallhaven").is_dir()
    for binary in (result["main"], result["helper"]):
        assert binary.stat().st_mode & stat.S_IXUSR


def test_build_appdir_apprun_points_at_main(tmp_path):
    """AppRun launches the bundled onedir binary with args."""
    dist, icon = _fake_dist(tmp_path)

    result = build_appdir(dist=dist, icon_png=icon)

    apprun = result["apprun"].read_text(encoding="utf-8")
    assert "usr/bin/ywallhaven/ywallhaven" in apprun
    assert '"$@"' in apprun


def test_build_appdir_desktop_has_required_keys(tmp_path):
    """Desktop entry carries every key appimagetool/lint needs."""
    dist, icon = _fake_dist(tmp_path)

    result = build_appdir(dist=dist, icon_png=icon)

    content = result["desktop"].read_text(encoding="utf-8")
    assert validate_desktop(content) == []


def test_build_appdir_missing_build_fails(tmp_path):
    """Missing PyInstaller output fails with a clear error."""
    import pytest

    dist = tmp_path / "dist"
    dist.mkdir()
    icon = tmp_path / "icon.png"
    icon.write_bytes(b"png")

    with pytest.raises(FileNotFoundError):
        build_appdir(dist=dist, icon_png=icon)


def test_build_appdir_missing_icon_fails(tmp_path):
    """Missing icon fails instead of staging a broken AppDir."""
    import pytest

    dist, _icon = _fake_dist(tmp_path)

    with pytest.raises(FileNotFoundError):
        build_appdir(
            dist=dist, icon_png=tmp_path / "nope.png"
        )
