"""Tests for the portable release packager (no network, tmp dirs)."""

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, "scripts")

from package_release import main, package


def _fake_dist(tmp_path: Path) -> Path:
    """Build a fake dist/ with two dummy executables."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "ywallhaven.exe").write_bytes(b"app" * 100)
    (dist / "ywallhaven-updater.exe").write_bytes(b"helper" * 100)
    return dist


def test_package_builds_zip_with_folder_and_sums(tmp_path):
    dist = _fake_dist(tmp_path)

    result = package(dist, "v0.11.0")

    zip_path = result["zip"]
    assert zip_path == dist / "ywallhaven_portable-v0.11.0.zip"
    with zipfile.ZipFile(zip_path) as archive:
        assert sorted(archive.namelist()) == [
            "ywallhaven/",
            "ywallhaven/ywallhaven-updater.exe",
            "ywallhaven/ywallhaven.exe",
        ]

    sums = (dist / "SHA256SUMS.txt").read_text(encoding="utf-8").split()
    assert len(sums) == 6  # three "hash  name" pairs
    assert sums[1] == "ywallhaven.exe"
    assert sums[3] == "ywallhaven-updater.exe"
    assert sums[5] == zip_path.name
    assert len(sums[0]) == 64
    assert sums[0] != sums[2]


def test_package_replaces_previous_run(tmp_path):
    dist = _fake_dist(tmp_path)

    package(dist, "v0.11.0")
    result = package(dist, "v0.11.0")

    assert result["zip"].is_file()
    assert (dist / "SHA256SUMS.txt").is_file()


def test_package_missing_exe_raises(tmp_path):
    import pytest

    dist = tmp_path / "dist"
    dist.mkdir()

    with pytest.raises(FileNotFoundError):
        package(dist, "v0.11.0")


def test_main_usage_error():
    assert main(["package_release.py"]) == 2
