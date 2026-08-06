"""Flet application entry point: builds the main UI layout."""

import asyncio
from io import BytesIO
from typing import Any

from flet import (
    Colors,
    Container,
    FilePicker,
    FilePickerFileType,
    Page,
    Row,
    SafeArea,
    SnackBar,
    SnackBarBehavior,
    Text,
)
from PIL import Image

from app.core import get_logger
from app.interface.components import LeftPanel, MiddlePanel, RightPanel

_lg = get_logger()


def _resize_image(data: bytes, size: tuple[int, int]) -> bytes | None:
    """Resize downloaded image bytes down to the requested size.

    Args:
        data: Original wallpaper file bytes.
        size: Target (width, height) to fit within.

    Returns:
        Resized image bytes, or None if resizing is not possible.
    """
    try:
        image = Image.open(BytesIO(data))
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
    snack = SnackBar(
        content=Text(message),
        open=True,
        behavior=SnackBarBehavior.FLOATING,
        bgcolor=Colors.RED if is_error else Colors.GREEN,
    )
    page.overlay.append(snack)
    snack.update()


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

    def on_page_error(e) -> None:
        """Log any unhandled exception happening on the page.

        Args:
            e: Error event from the Flet client.
        """
        _lg.critical(f"Page error: {e}.")

    page.on_error = on_page_error

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

        saved = await file_picker.save_file(
            dialog_title="Save wallpaper",
            file_name=file_name,
            file_type=FilePickerFileType.CUSTOM,
            allowed_extensions=["jpg", "png", "gif", "webp", "bmp"],
            src_bytes=data,
        )
        if saved:
            _show_snack(page, "Wallpaper downloaded")

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

    page.add(
        SafeArea(
            expand=True,
            content=Container(
                border_radius=10,
                content=Row(
                    spacing=8,
                    controls=[left_panel, middle_panel, right_panel],
                ),
            ),
        )
    )