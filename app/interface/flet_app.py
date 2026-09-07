"""Flet application entry point: builds the main UI layout."""

import asyncio
import shutil
import sys
from io import BytesIO
from pathlib import Path
from typing import Any

from flet import (
    Border,
    Card,
    ClipBehavior,
    Colors,
    Column,
    Container,
    Divider,
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
    VerticalDivider,
)
from PIL import Image as PILImage

from app.core import config, get_logger
from app.core.error_handling import install_loop_exception_handler
from app.core.resources import close_all
from app.interface.components import (
    LeftPanel,
    MiddlePanel,
    RightPanel,
    SettingsPanel,
)
from app.interface.components.update_dialog import check_and_offer
from app.interface.themes import apply_theme, get_theme, list_themes

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


def _bind_file_pickers(page: Page) -> tuple[FilePicker, FilePicker]:
    """Create the save + theme import pickers and keep them alive.

    In flet 0.86+ ``FilePicker`` is a service: constructing it registers
    the instance into ``page._services`` automatically, and it must not
    be added to ``page.overlay`` -- the client has no widget for
    ``FilePicker`` and renders "unknown control: FilePicker" if it is
    placed into the page control tree. The session also garbage-collects
    services with too few strong references after every event, so both
    pickers are pinned as page attributes for the whole session.

    Args:
        page: The Flet page to attach the pickers to.

    Returns:
        The save and theme pickers.
    """
    file_picker = FilePicker()
    theme_picker = FilePicker()
    page._ywallhaven_file_picker = file_picker
    page._ywallhaven_theme_picker = theme_picker
    _lg.info(
        f"FilePicker services bound: save={file_picker} "
        f"theme={theme_picker} (registered into page._services, "
        "not page.overlay)."
    )
    return file_picker, theme_picker


def _log_flet_client_diagnostics() -> None:
    """Log and auto-clean corrupted Flet desktop client cache.

    ``unknown control: <Name>`` errors almost always mean the running
    Flutter client build doesn't match the Python ``flet`` package
    version. ``flet_desktop`` caches under
    ``~/.flet/client/flet-desktop-<flavor>-<version>``. Option A
    auto-cleanup: delete only if empty or missing exe (safe, never
    deletes healthy 30MB cache).
    """
    try:
        from flet.version import flet_version

        cache_root = Path.home() / ".flet" / "client"
        matches = (
            sorted(cache_root.glob(f"flet-desktop-*-{flet_version}"))
            if cache_root.is_dir()
            else []
        )
        # Auto-cleanup A: empty or missing exe
        for m in matches:
            try:
                # Heuristic: empty dir or no executable inside
                has_content = any(m.iterdir())
                has_exe = any(m.rglob("*.exe")) or any(m.rglob("flet*"))
                if not has_content or not has_exe:
                    shutil.rmtree(m, ignore_errors=True)
                    _lg.warning(f"Cleared corrupted Flet cache {m}")
                    # Recompute matches after cleanup
                    matches = (
                        sorted(cache_root.glob(f"flet-desktop-*-{flet_version}"))
                        if cache_root.is_dir()
                        else []
                    )
            except Exception as e:
                _lg.debug(f"Cache cleanup failed for {m}: {e}")

        match_names = sorted(p.name for p in matches) if matches else []
        _lg.info(
            f"Flet client check: package_version={flet_version}, "
            f"matching_cache_dirs={match_names or 'none'}. "
            "If 'unknown control' persists, delete "
            f"{cache_root} and restart."
        )
    except Exception as e:
        _lg.debug(f"Could not inspect Flet client cache: {e}")


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
        # Pillow 11: Image.LANCZOS removed -> Resampling.LANCZOS
        lanczos = getattr(PILImage, "LANCZOS", getattr(getattr(PILImage, "Resampling", None), "LANCZOS", 1))
        image.thumbnail((size[0], size[1]), lanczos)
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
    install_loop_exception_handler()
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
    page.padding = 12
    page.bgcolor = Colors.SURFACE
    # Apply theme from registry (supports builtin + user themes)
    try:
        applied = apply_theme(page, config.data.THEME)
        _lg.debug(
            f"Theme applied: {applied.id} mode={applied.mode} seed={applied.seed}"
        )
    except Exception as e:
        _lg.warning(f"Failed to apply theme {config.data.THEME}: {e}")
        try:
            apply_theme(page, "dark_default")
        except Exception:
            pass

    def on_page_error(e) -> None:
        """Log any unhandled exception happening on the page.

        Args:
            e: Error event from the Flet client.
        """
        msg = str(getattr(e, "data", e))
        if "FilePicker" in msg or "unknown control" in msg.lower():
            _lg.critical(
                f"FilePicker unknown control at flet_app.py:220 "
                f"overlay={[type(s).__name__+':'+str(getattr(s, 'uid', '?')) for s in page.overlay]} msg={msg} e={e}",
                exc_info=True,
            )
        else:
            _lg.critical(f"Page error: {e}", exc_info=True)

    page.on_error = on_page_error

    def on_disconnect(e) -> None:
        """Release the registered resources before the session dies.

        Args:
            e: Disconnect event from the Flet client.
        """
        _lg.debug("Session disconnected; closing resources...")
        page.run_task(close_all)

    page.on_disconnect = on_disconnect

    file_picker, theme_picker = _bind_file_pickers(page)
    _log_flet_client_diagnostics()

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
        if size is not None:
            _lg.info(
                f"Downloading {file_name} "
                f"(resize: {size[0]}x{size[1]})."
            )
        else:
            _lg.info(f"Downloading {file_name} (original size).")
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
        _lg.debug(
            f"FilePicker save_file start at flet_app.py:304 "
            f"overlay={[type(s).__name__ for s in page.overlay]} web={getattr(page, 'web', False)} file={file_name}"
        )
        try:
            saved = await file_picker.save_file(
                dialog_title="Save wallpaper",
                file_name=file_name,
                file_type=FilePickerFileType.CUSTOM,
                allowed_extensions=["jpg", "png", "gif", "webp", "bmp"],
                src_bytes=data,
            )
            _lg.debug(f"FilePicker save_file returned {saved!r} at flet_app.py:304")
        except Exception as e:
            _lg.error(
                f"Save dialog failed at flet_app.py:304 overlay={[type(s).__name__ for s in page.overlay]} web={getattr(page, 'web', False)}",
                exc_info=True,
            )
            _show_snack(page, "Save failed", is_error=True)
            return

        if saved:
            _lg.info(
                f"Wallpaper saved as {saved} "
                f"({len(data)} bytes)."
            )
            _show_snack(page, "Wallpaper downloaded")
        else:
            _lg.info(f"Save cancelled by the user ({file_name}).")
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
        _lg.debug(f"Tag clicked: {tag_name!r}.")
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

    def on_api_key_change(api_key: str) -> None:
        """Propagate the API key from the settings to both panels.

        Args:
            api_key: New Wallhaven API key or an empty string.
        """
        left_panel.set_api_key(api_key)
        right_panel.set_api_key(api_key)

    settings_panel = SettingsPanel(
        on_api_key_change=on_api_key_change,
        theme_picker=theme_picker,
    )

    icon_bytes = _app_icon_bytes()
    logo = (
        Image(src=icon_bytes, width=32, height=32)
        if icon_bytes is not None
        else Icon(Icons.WALLPAPER, size=26)
    )
    current_theme = get_theme(config.data.THEME)
    theme_label = current_theme.name if current_theme else config.data.THEME

    # C3: polished header as surface container card + divider
    header = Container(
        bgcolor=Colors.SURFACE_CONTAINER,
        border_radius=16,
        padding=12,
        content=Row(
            spacing=12,
            vertical_alignment="center",
            controls=[
                logo,
                Text(
                    "ywallhaven",
                    size=20,
                    weight="w700",
                ),
                Container(
                    padding=6,
                    border_radius=20,
                    bgcolor=Colors.SURFACE_CONTAINER_HIGHEST,
                    content=Text(
                        theme_label,
                        size=11,
                        weight="w500",
                        color=Colors.ON_SURFACE_VARIANT,
                    ),
                ),
                Container(expand=True, content=Text("")),
                IconButton(
                    icon=Icons.SETTINGS,
                    icon_size=22,
                    tooltip="Settings",
                    style=None,
                    bgcolor=Colors.SURFACE_CONTAINER_HIGHEST,
                    on_click=settings_panel.toggle_settings,
                ),
            ],
        ),
    )

    # Wrap side panels in Card-like containers for C3 hierarchy
    left_wrapped = Container(
        expand=1,
        border=Border.all(1, Colors.OUTLINE_VARIANT),
        border_radius=16,
        clip_behavior=ClipBehavior.HARD_EDGE,
        content=left_panel,
    )
    middle_wrapped = Container(
        expand=3,
        border_radius=16,
        clip_behavior=ClipBehavior.HARD_EDGE,
        bgcolor=Colors.SURFACE_CONTAINER_LOW,
        padding=8,
        content=middle_panel,
    )
    right_wrapped = Container(
        expand=1,
        border=Border.all(1, Colors.OUTLINE_VARIANT),
        border_radius=16,
        clip_behavior=ClipBehavior.HARD_EDGE,
        content=right_panel,
    )

    # Responsive grid: adjust runs_count on resize
    def _on_resize(e) -> None:
        try:
            w = page.width or 1200
            if w < 900:
                middle_panel.runs_count = 2
            elif w < 1200:
                middle_panel.runs_count = 3
            else:
                middle_panel.runs_count = 4
            middle_panel.update()
        except Exception:
            pass

    page.on_resized = _on_resize

    page.add(
        SafeArea(
            expand=True,
            content=Column(
                spacing=12,
                expand=True,
                controls=[
                    header,
                    Divider(height=1, color=Colors.OUTLINE_VARIANT),
                    Row(
                        spacing=12,
                        expand=True,
                        controls=[
                            left_wrapped,
                            middle_wrapped,
                            right_wrapped,
                        ],
                    ),
                ],
            ),
        )
    )
    page.overlay.append(settings_panel)

    _lg.info(
        f"UI ready: theme={config.data.THEME}, "
        f"check_updates={config.data.CHECK_UPDATES}."
    )

    if config.data.CHECK_UPDATES:
        page.run_task(check_and_offer, page, manual=False)