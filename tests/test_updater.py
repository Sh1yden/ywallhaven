"""Tests for the updater service and the standalone updater helper."""

import hashlib
import json
import os
import sys
from pathlib import Path

import httpx
import pytest

from app.service import UpdaterService
from app.schemas import AssetInfo

API_BODY_200 = "https://api.github.com/repos/Sh1yden/ywallhaven/releases"


def release_payload(
    tag: str,
    *,
    prerelease: bool = False,
    asset_name: str = "ywallhaven.exe",
    include_digest: bool = True,
) -> dict:
    """Build a fake GitHub release payload."""
    digest = (
        f"sha256:{hashlib.sha256(b'exe').hexdigest()}"
        if include_digest
        else ""
    )
    return {
        "tag_name": tag,
        "prerelease": prerelease,
        "published_at": "2026-08-01T00:00:00Z",
        "body": "Release notes",
        "assets": [
            {
                "name": asset_name,
                "browser_download_url": f"{API_BODY_200}/download/{tag}/{asset_name}",
                "digest": digest,
            }
        ],
    }


def convert_asset(raw: dict) -> dict:
    """Rename browser_download_url to the schema field url."""
    return {**raw, "url": raw["browser_download_url"]}


def make_updater(
    payloads: list[dict],
    *,
    current_version: str = "0.5.0",
    check_prereleases: bool = False,
) -> UpdaterService:
    """Build an UpdaterService with a mocked GitHub API transport."""
    updater = UpdaterService(
        current_version=current_version,
        check_prereleases=check_prereleases,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payloads)

    updater.client = httpx.AsyncClient(
        base_url=UpdaterService.API_URL,
        transport=httpx.MockTransport(handler),
    )
    return updater


@pytest.mark.asyncio
async def test_returns_newer_release():
    payloads = [release_payload("v0.6.0")]
    updater = make_updater(payloads)

    release = await updater.check_update()

    assert release is not None
    assert release.tag_name == "v0.6.0"
    assert release.version == "0.6.0"
    await updater.close()


@pytest.mark.asyncio
async def test_returns_none_when_up_to_date():
    payloads = [release_payload("v0.5.0"), release_payload("v0.4.0")]
    updater = make_updater(payloads)

    release = await updater.check_update()

    assert release is None
    await updater.close()


@pytest.mark.asyncio
async def test_skips_prereleases_by_default():
    payloads = [
        release_payload("v0.7.0-rc1", prerelease=True),
        release_payload("v0.6.0"),
    ]
    updater = make_updater(payloads)

    release = await updater.check_update()

    assert release is not None
    assert release.tag_name == "v0.6.0"
    await updater.close()


@pytest.mark.asyncio
async def test_offers_prereleases_when_enabled():
    payloads = [release_payload("v0.7.0-rc1", prerelease=True)]
    updater = make_updater(payloads, check_prereleases=True)

    release = await updater.check_update()

    assert release is not None
    assert release.tag_name == "v0.7.0-rc1"
    await updater.close()


@pytest.mark.asyncio
async def test_skips_release_without_app_asset():
    payloads = [release_payload("v0.6.0", asset_name="other.exe")]
    updater = make_updater(payloads)

    release = await updater.check_update()

    assert release is None
    await updater.close()


@pytest.mark.asyncio
async def test_skips_release_with_invalid_tag():
    payloads = [release_payload("not-a-valid-tag")]
    updater = make_updater(payloads)

    release = await updater.check_update()

    assert release is None
    await updater.close()


@pytest.mark.asyncio
async def test_handles_api_error_gracefully():
    updater = UpdaterService(current_version="0.5.0")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    updater.client = httpx.AsyncClient(
        base_url=UpdaterService.API_URL,
        transport=httpx.MockTransport(handler),
    )

    release = await updater.check_update()

    assert release is None
    await updater.close()


@pytest.mark.asyncio
async def test_download_asset_writes_file():
    payloads = [release_payload("v0.6.0")]
    updater = make_updater(payloads)
    release = await updater.check_update()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-length": "3"},
            content=b"exe",
        )

    updater.client = httpx.AsyncClient(
        base_url=UpdaterService.API_URL,
        transport=httpx.MockTransport(handler),
    )

    path = await updater.download_asset(release)

    assert path is not None
    assert path.read_bytes() == b"exe"
    path.unlink(missing_ok=True)
    await updater.close()


def test_verify_sha256_matches():
    fake = Path("/tmp/fake-update.exe")
    fake.write_bytes(b"exe")
    asset = AssetInfo(**convert_asset(release_payload("v0.6.0")["assets"][0]))

    try:
        assert UpdaterService.verify_sha256(fake, asset)
    finally:
        fake.unlink(missing_ok=True)


def test_verify_sha256_rejects_mismatch():
    fake = Path("/tmp/fake-update2.exe")
    fake.write_bytes(b"other")
    asset = AssetInfo(**convert_asset(release_payload("v0.6.0")["assets"][0]))

    try:
        assert not UpdaterService.verify_sha256(fake, asset)
    finally:
        fake.unlink(missing_ok=True)


def test_verify_sha256_rejects_missing_digest():
    fake = Path("/tmp/fake-update3.exe")
    fake.write_bytes(b"exe")
    asset = AssetInfo(**convert_asset(release_payload("v0.6.0", include_digest=False)["assets"][0]))

    try:
        assert not UpdaterService.verify_sha256(fake, asset)
    finally:
        fake.unlink(missing_ok=True)


# Standalone updater helper ----------------------------------------

from updater.main import _process_alive, _wait_for_exit


def test_process_alive_for_own_pid():
    assert _process_alive(os.getpid()) is True


def test_process_alive_for_dead_pid():
    assert _process_alive(2**31 - 1) is False


def test_wait_for_exit_timeouts():
    assert _wait_for_exit(os.getpid(), timeout=0.1, logger=None) is False


def test_wait_for_exit_returns_immediately_for_dead_pid():
    assert _wait_for_exit(2**31 - 1, timeout=0.1, logger=None) is True


def test_replace_logic(tmp_path: Path):
    from updater.main import main as updater_main

    src = tmp_path / "new.exe"
    dst = tmp_path / "app.exe"
    src.write_bytes(b"new")
    dst.write_bytes(b"old")

    old_argv = sys.argv
    sys.argv = [
        "updater",
        "--pid", str(2**31 - 1),
        "--src", str(src),
        "--dst", str(dst),
        "--log", str(tmp_path / "updater.log"),
    ]
    try:
        exit_code = updater_main()
    finally:
        sys.argv = old_argv

    assert exit_code == 0
    assert dst.read_bytes() == b"new"