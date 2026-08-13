"""Async updater service backed by the GitHub releases API."""

import hashlib
import os
from pathlib import Path
from subprocess import Popen
from tempfile import gettempdir
from typing import Callable

from httpx import AsyncClient, HTTPError
from packaging.version import InvalidVersion, Version

from app.core import LoggerMixin, config
from app.core.version import __version__
from app.schemas import AssetInfo, ReleaseInfo

ProgressCallback = Callable[[int, int], None]


class UpdaterError(Exception):
    """Raised when an update cannot be checked or applied."""


class UpdaterService(LoggerMixin):
    """Check GitHub releases, download and install the new executable.

    The downloaded ``ywallhaven.exe`` is handed over to the standalone
    ``ywallhaven-updater.exe`` helper, which waits for this process to
    exit, replaces the running executable and restarts the app.
    """

    REPO = "Sh1yden/ywallhaven"
    API_URL = f"https://api.github.com/repos/{REPO}/releases"
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
        """
        try:
            response = await self.client.get("", params={"per_page": self.PER_PAGE})
            response.raise_for_status()
        except HTTPError as e:
            self._lg.error(f"Failed to fetch releases from GitHub: {e}.")
            return None

        for raw_release in response.json():
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
                self._lg.debug(
                    f"Update available: {remote_version} > {self.current_version}."
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

                with open(target, "wb") as f:
                    async for chunk in response.aiter_bytes(self.CHUNK_SIZE):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress is not None:
                            progress(downloaded, total)
            self._lg.debug(f"Downloaded {downloaded} bytes.")
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
            return False

        digest = asset.digest.removeprefix("sha256:").strip().lower()
        sha256 = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(UpdaterService.CHUNK_SIZE), b""):
                    sha256.update(chunk)
        except OSError:
            return False

        return sha256.hexdigest() == digest

    # Applying -----------------------------------------------------

    def launch_updater(self, downloaded: Path) -> bool:
        """Hand the new executable to the ywallhaven-updater helper.

        Args:
            downloaded: Verified path of the new executable.

        Returns:
            True when the helper was started successfully.
        """
        if not getattr(sys, "frozen", False):
            self._lg.error(
                "Cannot apply an update when running from sources."
            )
            return False

        exe_path = Path(sys.executable).resolve()
        if downloaded.resolve() == exe_path:
            self._lg.error("Refusing to update with the same file.")
            return False

        helper = exe_path.parent / "ywallhaven-updater.exe"
        if not helper.is_file():
            self._lg.error(f"Updater helper not found: {helper}.")
            return False

        log_path = exe_path.parent / "ywallhaven_updater.log"
        command = [
            str(helper),
            "--pid", str(os.getpid()),
            "--src", str(downloaded),
            "--dst", str(exe_path),
            "--log", str(log_path),
            "--restart",
        ]
        try:
            Popen(
                command,
                cwd=str(exe_path.parent),
                creationflags=(
                    0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
                ),
            )
            self._lg.info("Updater helper started; shutting down...")
            return True
        except OSError as e:
            self._lg.error(f"Failed to start the updater helper: {e}.")
            return False

    async def __aenter__(self) -> "UpdaterService":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()