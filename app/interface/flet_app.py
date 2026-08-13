"""Flet application entry point: builds the main UI layout."""

import asyncio
import sys
from io import BytesIO
from pathlib import Path
from typing import Any

from flet import (
    Colors,
    Column,
    Container,
    FilePicker,
    FilePickerFileType,
    Icon,
    IconButton,
    Icons,
    Image,
    Page,
    Row,
    SafeArea,
    SnackBar,
    SnackBarBehavior,
    Text,
    ThemeMode,
)
from PIL import Image as PILImage

from app.core import config, get_logger
from app.core.resources import close_all
from app.interface.components import (
    LeftPanel,
    MiddlePanel,
    RightPanel,
    SettingsPanel,
)
from app.interface.components.update_dialog import check_and_offer

_lg = get_logger()


def _candidate_icon_paths() -> tuple[Path, ...]:
    """Return the paths where the bundled app icon may live.

    Order matters: PyInstaller onefile extracts data into ``sys._MEIPASS``,
    then the source-tree location, then the working directory. PNG is
    preferred: the Flet (Flutter) client does not render SVG files.
    """
    roots = [
        Path(getattr(sys, "_MEIPASS", None)) if getattr(sys, "_MEIPASS", None) else None,
        Path(__file__).resolve().parent.parent.parent,
        Path.cwd(),
    ]
    candidates: list[Path] = []
    for root in roots:
        if root is None:
            continue
        candidates.append(root / "assets" / "icon.png")
        candidates.append(root / "assets" / "icon.svg")
    return tuple(dict.fromkeys(candidates))


def _app_icon_bytes() -> bytes | None:
    """Read the bundled app icon as bytes for the header logo.

    Returns:
        Parsed raw bytes of assets/icon.svg, or None if unavailable.
    """
    for icon_path in _candidate_icon_paths():
        try:
            return icon_path.read_bytes()
        except FileNotFoundError:
            continue
        except Exception as e:
            _lg.error(f"Failed to load app icon from {icon_path}: {e}.")
            return None
    _lg.error("App icon not found in any candidate location.")
    return None


def _resize_image(data: bytes, size: tuple[int, int]) -> bytes | None:
    """Resize downloaded image bytes down to the requested size.

    Args:
        data: Original wallpaper file bytes.
        size: Target (width, height) to fit within.

    Returns:
        Resized image bytes, or None if resizing is not possible.
    """
    try:
        image = PILImage.open(BytesIO(data))
        if getattr(image, "is_animated", False):
            return None
        image.thumbnail((size[0], size[1]), Image.LANCZOS)
        output = BytesIO()
        if image.mode in ("RGBA", "LA", "P"):
            image = image.convert("RGBA")
            image.save(output, format="PNG")
        else:
            image = image.convert("RGB")
            image.save(output, format="JPEG", quality=85)
        return output.getvalue()
    except Exception as e:
        _lg.error(f"Failed to resize wallpaper: {e}.")
        return None


def _show_snack(page: Page, message: str, is_error: bool = False) -> None:
    """Show a transient status message.

    Args:
        page: The Flet page.
        message: Text to display.
        is_error: Whether to style the snack as an error.
    """
    page.show_dialog(
        SnackBar(
            content=Text(message),
            behavior=SnackBarBehavior.FLOATING,
            bgcolor=Colors.RED if is_error else Colors.GREEN,
        )
    )


async def flet_main(page: Page):
    """Build and mount the main three-panel layout on the page.

    Args:
        page: The Flet page to render the UI into.
    """
    _lg.debug("flet_main called...")
    try:
        await _build_ui(page)
    except Exception as e:
        _lg.critical(f"flet_main failed: {e}", exc_info=True)
        raise


async def _build_ui(page: Page) -> None:
    """Build and mount the main three-panel layout on the page.

    Args:
        page: The Flet page to render the UI into.
    """
    _lg.debug(f"Building UI for session...")

    page.title = "ywallhaven"
    page.padding = 10
    page.theme_mode = (
        ThemeMode.LIGHT if config.data.THEME == "light" else ThemeMode.DARK
    )

    def on_page_error(e) -> None:
        """Log any unhandled exception happening on the page.

        Args:
            e: Error event from the Flet client.
        """
        _lg.critical(f"Page error: {e}.")

    page.on_error = on_page_error

    def on_disconnect(e) -> None:
        """Release the registered resources before the session dies.

        Args:
            e: Disconnect event from the Flet client.
        """
        _lg.debug("Session disconnected; closing resources...")
        page.run_task(close_all)

    page.on_disconnect = on_disconnect

    file_picker = FilePicker()

    async def save_wallpaper(
        url: str,
        file_name: str,
        size: tuple[int, int] | None = None,
    ) -> None:
        """Download the wallpaper bytes and open the save dialog.

        Args:
            url: Full-size wallpaper URL.
            file_name: Suggested file name.
            size: Optional target resolution for a downscaled copy.
        """
        data = await middle_panel.api_client.fetch_bytes(url)
        if data is None:
            _show_snack(page, "Download failed", is_error=True)
            return

        if size is not None:
            resized = await asyncio.to_thread(_resize_image, data, size)
            if resized is not None:
                data = resized
                _lg.debug(f"Wallpaper resized to {size[0]}x{size[1]}.")

        saved = None
        try:
            saved = await file_picker.save_file(
                dialog_title="Save wallpaper",
                file_name=file_name,
                file_type=FilePickerFileType.CUSTOM,
                allowed_extensions=["jpg", "png", "gif", "webp", "bmp"],
                src_bytes=data,
            )
        except Exception as e:
            _lg.error(f"Save dialog failed: {e}.")
            _show_snack(page, "Save failed", is_error=True)
            return

        if saved:
            _show_snack(page, "Wallpaper downloaded")
        else:
            _show_snack(page, "Save cancelled")

    def request_save(
        url: str, file_name: str, size: tuple[int, int] | None = None
    ) -> None:
        """Launch the download task for the given wallpaper.

        Args:
            url: Full-size wallpaper URL.
            file_name: Suggested file name.
            size: Optional target resolution for a downscaled copy.
        """
        page.run_task(save_wallpaper, url, file_name, size)

    def on_tag_click(tag_name: str) -> None:
        """Search for the clicked tag in the gallery.

        Args:
            tag_name: Tag name to search for.
        """
        left_panel.search_tag(tag_name)

    def on_navigate(delta: int, index: int | None) -> Any:
        """Move to an adjacent wallpaper in the loaded gallery.

        Args:
            delta: Offset from the current wallpaper.
            index: Current wallpaper index in the cache.

        Returns:
            The resolved wallpaper index.
        """
        return middle_panel.select_relative(delta, index)

    right_panel = RightPanel(
        on_download=request_save,
        on_tag_click=on_tag_click,
        on_navigate=on_navigate,
    )
    middle_panel = MiddlePanel(
        right_panel=right_panel,
    )
    left_panel = LeftPanel(middle_panel)
    settings_panel = SettingsPanel(
        on_api_key_change=left_panel.set_api_key,
    )

    icon_bytes = _app_icon_bytes()
    logo = (
        Image(src=icon_bytes, width=28, height=28)
        if icon_bytes is not None
        else Icon(Icons.WALLPAPER, size=24)
    )
    header = Row(
        spacing=8,
        controls=[
            logo,
            Text(
                "ywallhaven",
                size=16,
                weight="w700",
            ),
            IconButton(
                icon=Icons.SETTINGS,
                icon_size=22,
                tooltip="Settings",
                on_click=settings_panel.toggle_settings,
            ),
        ],
    )

    page.add(
        SafeArea(
            expand=True,
            content=Container(
                border_radius=10,
                content=Column(
                    spacing=8,
                    expand=True,
                    controls=[
                        header,
                        Row(
                            spacing=8,
                            expand=True,
                            controls=[
                                left_panel,
                                middle_panel,
                                right_panel,
                            ],
                        ),
                    ],
                ),
            ),
        )
    )
    page.overlay.append(settings_panel)

    if config.data.CHECK_UPDATES:
        page.run_task(check_and_offer, page, manual=False)