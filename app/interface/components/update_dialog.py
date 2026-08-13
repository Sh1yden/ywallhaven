"""Update dialog: offer, download and apply application updates."""

import asyncio
from pathlib import Path
from typing import Any

from flet import (
    AlertDialog,
    Column,
    Colors,
    Container,
    FilledButton,
    Icon,
    Icons,
    MainAxisAlignment,
    ProgressBar,
    Row,
    SnackBar,
    SnackBarBehavior,
    Text,
    TextButton,
)

from app.core import get_logger
from app.core.error_handling import guard
from app.core.version import __version__
from app.schemas import ReleaseInfo
from app.service import UpdaterService

_lg = get_logger()

_check_lock = asyncio.Lock()
_startup_checked = False

_BODY_MAX_LENGTH = 400


async def check_and_offer(page: Any, *, manual: bool = False) -> None:
    """Check GitHub for an update and offer it to the user.

    Args:
        page: The Flet page.
        manual: Whether the check was triggered by the user; when
            False the check runs silently once per application session.
    """
    global _startup_checked

    if not manual and _startup_checked:
        _lg.debug("Startup update check skipped (already done).")
        return
    _startup_checked = True

    if _check_lock.locked():
        _lg.debug("Update check skipped (another check is running).")
        return

    if manual:
        _lg.info("Checking for updates...")
    else:
        _lg.debug("Checking for updates on startup...")

    async with _check_lock:
        updater = UpdaterService()
        try:
            release = await updater.check_update()
        except Exception as e:
            _lg.error(f"Update check failed: {e}.", exc_info=True)
            await updater.close()
            if manual:
                UpdateDialog.show_message(page, "Update check failed", True)
            return

        if release is None:
            await updater.close()
            if manual:
                _lg.info("Update check finished: up to date.")
                UpdateDialog.show_message(page, "Up to date")
            else:
                _lg.debug("Update check finished: up to date.")
            return

        _lg.info(f"Offering update to {release.version}.")
        UpdateDialog(page, updater, release).open()


class UpdateDialog:
    """Modal dialog driving the whole update flow.

    Shows the release notes, downloads the new executable with a
    progress bar, verifies its checksum and hands it over to the
    updater helper before closing the application window.
    """

    def __init__(
        self,
        page: Any,
        updater: UpdaterService,
        release: ReleaseInfo,
    ) -> None:
        self.page = page
        self.updater = updater
        self.release = release

        self._busy = False
        self._update_btn = FilledButton(
            content="Update",
            on_click=self._on_update_click,
        )
        self._later_btn = TextButton(
            content="Later",
            on_click=lambda e: self._close(),
        )
        self._status = Text(
            f"Version {release.version} is available "
            f"(you have {__version__}).",
        )
        self._progress = ProgressBar(value=0, visible=False)
        self._details = self._release_details(release)

        self._dialog = AlertDialog(
            modal=True,
            title=Text("Update available"),
            content=Column(
                tight=True,
                spacing=8,
                controls=[
                    self._status,
                    self._details,
                    self._progress,
                ],
            ),
            actions=[
                self._later_btn,
                self._update_btn,
            ],
            actions_alignment=MainAxisAlignment.END,
        )

    def open(self) -> None:
        """Show the dialog on the page."""
        self.page.show_dialog(self._dialog)

    @staticmethod
    def show_message(page: Any, message: str, is_error: bool = False) -> None:
        """Show a status snack with an icon.

        Args:
            page: The Flet page.
            message: Text to display.
            is_error: Whether to style the snack as an error.
        """
        icon = Icons.ERROR_OUTLINE if is_error else Icons.CHECK_CIRCLE
        color = Colors.RED if is_error else Colors.GREEN
        page.show_dialog(
            SnackBar(
                content=Row(
                    spacing=10,
                    controls=[
                        Icon(icon, size=18),
                        Text(message, size=14),
                    ],
                ),
                bgcolor=color,
                behavior=SnackBarBehavior.FLOATING,
            )
        )

    # Private helpers ----------------------------------------------

    @staticmethod
    def _release_details(release: ReleaseInfo) -> Container:
        """Build the release notes block.

        Args:
            release: Release whose notes should be shown.

        Returns:
            Container with the truncated release body.
        """
        body = (release.body or "").strip()
        if len(body) > _BODY_MAX_LENGTH:
            body = body[:_BODY_MAX_LENGTH] + "..."
        return Container(
            content=Text(
                body or f"Release {release.tag_name}",
                color=Colors.ON_SURFACE_VARIANT,
                size=12,
            ),
        )

    def _close(self) -> None:
        """Close the dialog and release the updater client."""
        self.page.pop_dialog()
        self.page.run_task(self.updater.close)

    @guard
    def _on_update_click(self, e) -> None:
        """Disable the actions and start the update task.

        Args:
            e: Click event.
        """
        _lg.info(f"Update to {self.release.version} accepted by the user.")
        if self._busy:
            return
        self._busy = True
        self._update_btn.disabled = True
        self._later_btn.disabled = True
        self._progress.visible = True
        self._dialog.update()
        self.page.run_task(self._apply)

    def _on_progress(self, downloaded: int, total: int) -> None:
        """Refresh the progress bar during the download.

        Args:
            downloaded: Bytes downloaded so far.
            total: Expected total size in bytes (0 if unknown).
        """
        value = downloaded / total if total else None
        self._progress.value = value
        self._progress.update()

    def _set_error(self, message: str) -> None:
        """Show a terminal error state in the dialog.

        Args:
            message: Error text to display.
        """
        self._status.value = f"Update failed: {message}"
        self._status.color = Colors.RED
        self._update_btn.disabled = True
        self._later_btn.content = "Close"
        self._later_btn.disabled = False
        self._dialog.update()

    async def _apply(self) -> None:
        """Download, verify and install the new executable."""
        try:
            await self._install()
        except Exception as e:
            _lg.error(f"Update failed: {e}.", exc_info=True)
            self._set_error(str(e))

    async def _install(self) -> None:
        """Run the download -> verify -> launch pipeline."""
        path = await self._download()
        if path is None:
            return

        asset = self.updater.find_asset(self.release)
        if asset is None:
            self._set_error("release asset disappeared")
            return

        self._status.value = "Verifying..."
        self._status.update()
        if not self.updater.verify_sha256(path, asset):
            path.unlink(missing_ok=True)
            self._set_error("checksum mismatch")
            return

        self._status.value = "Restarting..."
        self._status.update()
        if not self.updater.launch_updater(path):
            path.unlink(missing_ok=True)
            self._set_error("updater helper unavailable")
            return

        await self.updater.close()
        await self.page.window.destroy()

    async def _download(self) -> Path | None:
        """Download the release asset.

        Returns:
            Path of the downloaded file, or None on failure.
        """
        self._status.value = "Downloading..."
        self._status.update()

        path = await self.updater.download_asset(
            self.release,
            progress=self._on_progress,
        )
        if path is None:
            self._set_error("download failed")
            return None
        return path