"""Flet application entry point: builds the main UI layout."""

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

from app.core import get_logger
from app.interface.components import LeftPanel, MiddlePanel, RightPanel

_lg = get_logger()


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

    page.title = "ywallhaven"
    page.padding = 10

    file_picker = FilePicker()

    async def save_wallpaper(url: str, file_name: str) -> None:
        """Download the wallpaper bytes and open the save dialog.

        Args:
            url: Full-size wallpaper URL.
            file_name: Suggested file name.
        """
        data = await middle_panel.api_client.fetch_bytes(url)
        if data is None:
            _show_snack(page, "Download failed", is_error=True)
            return

        saved = await file_picker.save_file(
            dialog_title="Save wallpaper",
            file_name=file_name,
            file_type=FilePickerFileType.CUSTOM,
            allowed_extensions=["jpg", "png", "gif", "webp", "bmp"],
            src_bytes=data,
        )
        if saved:
            _show_snack(page, "Wallpaper downloaded")

    def request_save(url: str, file_name: str) -> None:
        """Launch the download task for the given wallpaper.

        Args:
            url: Full-size wallpaper URL.
            file_name: Suggested file name.
        """
        page.run_task(save_wallpaper, url, file_name)

    right_panel = RightPanel(on_download=request_save)
    middle_panel = MiddlePanel(
        right_panel=right_panel, on_download=request_save
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