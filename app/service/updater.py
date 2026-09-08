"""Async updater service backed by the GitHub releases API."""

import hashlib
import os
import sys
from pathlib import Path
from subprocess import Popen
from tempfile import gettempdir
from typing import Callable

from httpx import AsyncClient, HTTPError
from packaging.version import InvalidVersion, Version

from app.core import LoggerMixin, config, get_logger
from app.core.logger_config import get_updater_logger
from app.core.version import __version__
from app.schemas import AssetInfo, ReleaseInfo

ProgressCallback = Callable[[int, int], None]

_lg = get_logger()
_upd_lg = get_updater_logger()


class UpdaterError(Exception):
    """Raised when an update cannot be checked or applied."""


class UpdaterService(LoggerMixin):
    """Check GitHub releases, download and install the new executable.

    The downloaded ``ywallhaven.exe`` is handed over to the standalone
    ``ywallhaven-updater.exe`` helper, which waits for this process to
    exit, replaces the running executable and restarts the app.
    """

    REPO = "Sh1yden/ywallhaven"
    API_URL = "https://api.github.com"
    ASSET_NAME = "ywallhaven.exe"
    REQUEST_TIMEOUT = 15.0
    CHUNK_SIZE = 64 * 1024
    PER_PAGE = 10

    def __init__(
        self,
        *,
        current_version: str = __version__,
        check_prereleases: bool | None = None,
    ) -> None:
        super().__init__()
        try:
            self.current_version = Version(current_version)
        except InvalidVersion:
            self._lg.warning(
                f"Unparsable current version {current_version!r}; using 0.0.0."
            )
            self.current_version = Version("0.0.0")

        self.check_prereleases = (
            config.data.CHECK_PRERELEASES
            if check_prereleases is None
            else check_prereleases
        )

        self.last_launch_error = ""

        self.client = AsyncClient(
            base_url=self.API_URL,
            timeout=self.REQUEST_TIMEOUT,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"ywallhaven/{current_version}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    async def close(self) -> None:
        """Close the underlying HTTP client session."""
        await self.client.aclose()

    # Checking -----------------------------------------------------

    async def check_update(self) -> ReleaseInfo | None:
        """Return the newest applicable release or None.

        Pre-releases are skipped unless enabled in the config. The
        release must contain an asset named ``ywallhaven.exe`` and its
        version must be newer than the running one.

        Raises:
            UpdaterError: When the GitHub API cannot be reached.
        """
        try:
            response = await self.client.get(
                f"/repos/{self.REPO}/releases",
                params={"per_page": self.PER_PAGE},
            )
            response.raise_for_status()
        except HTTPError as e:
            self._lg.error(f"Failed to fetch releases from GitHub: {e}.")
            raise UpdaterError("GitHub API request failed") from e

        releases = response.json()
        self._lg.debug(
            f"Received {len(releases)} releases from GitHub."
        )
        for raw_release in releases:
            release = self._parse_release(raw_release)
            if release is None:
                continue

            if not self.check_prereleases and release.prerelease:
                self._lg.debug(
                    f"Skipping pre-release {release.tag_name} "
                    "(CHECK_PRERELEASES is off)."
                )
                continue

            asset = self.find_asset(release)
            if asset is None:
                self._lg.debug(f"No {self.ASSET_NAME} asset in {release.tag_name}.")
                continue

            try:
                remote_version = Version(release.tag_name.lstrip("v"))
            except InvalidVersion:
                self._lg.debug(f"Skipping release with bad tag {release.tag_name}.")
                continue

            if remote_version > self.current_version:
                release.version = str(remote_version)
                self._lg.info(
                    f"Update available: {remote_version} > "
                    f"{self.current_version}."
                )
                return release

        self._lg.debug("No newer release found.")
        return None

    @staticmethod
    def _parse_release(raw: dict) -> ReleaseInfo | None:
        """Convert a raw GitHub release dict into a model.

        Returns:
            ReleaseInfo, or None if the payload is malformed.
        """
        try:
            return ReleaseInfo(
                tag_name=raw.get("tag_name", ""),
                prerelease=bool(raw.get("prerelease", False)),
                published_at=str(raw.get("published_at", "")),
                body=str(raw.get("body", "")),
                assets=[
                    AssetInfo(
                        name=asset.get("name", ""),
                        url=asset.get("browser_download_url", ""),
                        digest=str(asset.get("digest", "")),
                    )
                    for asset in raw.get("assets", [])
                ],
            )
        except Exception as e:
            _lg.debug(f"Skipping malformed release payload: {e}.")
            return None

    def find_asset(self, release: ReleaseInfo) -> AssetInfo | None:
        """Return the app asset of a release, or None."""
        return next(
            (a for a in release.assets if a.name == self.ASSET_NAME), None
        )

    # Downloading --------------------------------------------------

    async def download_asset(
        self,
        release: ReleaseInfo,
        *,
        progress: ProgressCallback | None = None,
    ) -> Path | None:
        """Download the release executable into the temp directory.

        Args:
            release: Release whose asset should be downloaded.
            progress: Optional callback receiving (downloaded, total).

        Returns:
            Path to the downloaded file, or None on failure.
        """
        asset = self.find_asset(release)
        if asset is None:
            self._lg.error(f"No {self.ASSET_NAME} asset in {release.tag_name}.")
            return None

        target = (
            Path(gettempdir())
            / f"ywallhaven-{release.tag_name.lstrip('v')}-update.exe"
        )
        total = 0
        downloaded = 0

        try:
            self._lg.debug(f"Downloading {asset.url} -> {target}...")
            async with self.client.stream("GET", asset.url, follow_redirects=True) as response:
                response.raise_for_status()
                total = int(response.headers.get("content-length", 0))
                _upd_lg.debug(
                    f"Download started: {asset.url}, total={total} bytes."
                )

                with open(target, "wb") as f:
                    last_percent = -1
                    async for chunk in response.aiter_bytes(self.CHUNK_SIZE):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress is not None:
                            progress(downloaded, total)
                        if total:
                            percent = downloaded * 100 // total
                            if percent // 25 != last_percent // 25:
                                last_percent = percent
                                self._lg.debug(
                                    f"Download progress: {percent}% "
                                    f"({downloaded}/{total} bytes)."
                                )
            self._lg.info(f"Downloaded {downloaded} bytes -> {target}.")
            _upd_lg.info(
                f"Update downloaded: {downloaded} bytes -> {target}."
            )
            return target
        except HTTPError as e:
            self._lg.error(f"Download failed: {e}.")
            target.unlink(missing_ok=True)
            return None
        except OSError as e:
            self._lg.error(f"Failed to write {target}: {e}.")
            target.unlink(missing_ok=True)
            return None

    # Verification -------------------------------------------------

    @staticmethod
    def verify_sha256(path: Path, asset: AssetInfo) -> bool:
        """Verify the downloaded file against the GitHub-provided digest.

        Args:
            path: Downloaded executable.
            asset: Release asset carrying the ``sha256:...`` digest.

        Returns:
            True when the file matches the digest.
        """
        if not asset.digest.startswith("sha256:"):
            _lg.debug(f"No sha256 digest for {asset.name}; skipping check.")
            return False

        digest = asset.digest.removeprefix("sha256:").strip().lower()
        sha256 = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                for chunk in iter(
                    lambda: f.read(UpdaterService.CHUNK_SIZE), b""
                ):
                    sha256.update(chunk)
        except OSError as e:
            _lg.error(f"Failed to read {path} for verification: {e}.")
            return False

        matches = sha256.hexdigest() == digest
        if matches:
            _upd_lg.debug(
                f"Checksum verified for {path} (sha256 matches)."
            )
        else:
            _upd_lg.error(
                f"Checksum mismatch for {path}:"
                f" expected sha256:{digest}."
            )
        return matches

    # Applying -----------------------------------------------------

    def launch_updater(self, downloaded: Path) -> bool:
        """Hand the new executable to the ywallhaven-updater helper.

        Args:
            downloaded: Verified path of the new executable.

        Returns:
            True when the helper was started successfully. On failure
            the concrete reason is stored in ``last_launch_error``.
        """
        self.last_launch_error = ""
        exe_path = Path(sys.executable).resolve()
        frozen = getattr(sys, "frozen", False)

        _upd_lg.debug(
            "launch_updater:"
            f" frozen={frozen}, executable={exe_path},"
            f" downloaded={downloaded}"
        )

        if not frozen:
            self._lg.error(
                "Cannot apply an update when running from sources."
            )
            _upd_lg.error(
                "Cannot apply an update when running from sources."
            )
            self.last_launch_error = (
                "not a packaged build (running from sources)"
            )
            return False

        if downloaded.resolve() == exe_path:
            self._lg.error("Refusing to update with the same file.")
            _upd_lg.error(
                f"Refusing to update: {downloaded} equals {exe_path}."
            )
            self.last_launch_error = (
                "downloaded file equals the running executable"
            )
            return False

        helper = exe_path.parent / "ywallhaven-updater.exe"
        _upd_lg.debug(f"Expecting updater helper at: {helper}.")
        if not helper.is_file():
            self._lg.error(f"Updater helper not found: {helper}.")
            _upd_lg.error(f"Updater helper not found: {helper}.")
            self.last_launch_error = f"updater helper not found: {helper}"
            return False

        log_path = exe_path.parent / "ywallhaven_updater.log"
        # Diagnostic: ensure the file exists before handing it over.
        try:
            exists = downloaded.is_file()
            size = downloaded.stat().st_size if exists else 0
            _upd_lg.debug(
                "Updater src check:"
                f" exists={exists}, size={size}, path={downloaded}"
            )
            if not exists:
                # List temp dir for debugging
                tmp_files = list(
                    Path(gettempdir()).glob("ywallhaven-*-update.exe")
                )
                self._lg.error(f"Temp update files present: {tmp_files}")
                _upd_lg.error(
                    f"Downloaded file disappeared: {downloaded}."
                    f" Leftover update files: {tmp_files}"
                )
                self.last_launch_error = (
                    "downloaded file disappeared before launch"
                )
                return False
        except Exception as e:
            _upd_lg.warning(f"Updater src check failed: {e}")

        command = [
            str(helper),
            "--pid", str(os.getpid()),
            "--src", str(downloaded),
            "--dst", str(exe_path),
            "--log", str(log_path),
            "--restart",
        ]
        _upd_lg.debug(f"Launching updater helper: {command}")
        try:
            Popen(
                command,
                cwd=str(exe_path.parent),
                creationflags=(
                    0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
                ),
            )
            _upd_lg.info("Updater helper started; shutting down...")
            self._lg.info("Updater helper started; shutting down...")
            return True
        except OSError as e:
            self._lg.error(f"Failed to start the updater helper: {e}.")
            _upd_lg.error(f"Failed to start the updater helper: {e}.")
            self.last_launch_error = f"failed to start updater helper: {e}"
            return False

    async def __aenter__(self) -> "UpdaterService":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()