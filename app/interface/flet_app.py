"""Flet application entry point: builds the main UI layout."""

import asyncio
import shutil
import sys
import time
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Dict, List

from flet import (
    AlertDialog,
    Border,
    Card,
    ClipBehavior,
    Colors,
    Column,
    Container,
    Divider,
    Dropdown,
    DropdownOption,
    FilePicker,
    FilePickerFileType,
    FilledButton,
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
    TextButton,
    TextField,
    VerticalDivider,
)
from PIL import Image as PILImage

from app.core import config, get_logger
from app.core.error_handling import install_loop_exception_handler
from app.core.resources import close_all
from app.interface import bus
from app.interface.components import (
    CollectionSettingsPanel,
    CollectionsPanel,
    LeftPanel,
    MiddlePanel,
    RightPanel,
    SettingsPanel,
)
from app.interface.components.collections_panel import ICON_PRESETS
from app.interface.components.update_dialog import check_and_offer
from app.interface.themes import apply_theme, get_theme, list_themes
from app.service.collection_io import (
    build_zip,
    display_name,
    resolve_bytes,
    unique_name,
)
from app.service.favorites import FAVORITES_ID, FavoritesStore
from app.service.slideshow import SlideshowService
from app.service.wallpaper import (
    is_supported as is_wallpaper_supported,
    set_wallpaper_from_url,
)

_lg = get_logger()


def _candidate_icon_paths() -> tuple[Path, ...]:
    """Return the paths where the bundled app icon may live.

    Order matters: PyInstaller onefile extracts data into ``sys._MEIPASS``,
    then the source-tree location, then the working directory. The ``.ico``
    is listed first as the native Windows window icon, then PNG for the
    header logo (the Flet/Flutter client does not render SVG files).
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
        candidates.append(root / "docs" / "assets" / "icon.ico")
        candidates.append(root / "docs" / "assets" / "icon.png")
        candidates.append(root / "docs" / "assets" / "icon.svg")
    return tuple(dict.fromkeys(candidates))


def _window_icon_path() -> str | None:
    """Return the first existing icon path usable for the OS window.

    Returns:
        Absolute path of the window icon, or None if none is available.
    """
    for icon_path in _candidate_icon_paths():
        if icon_path.is_file():
            return str(icon_path)
    return None


def _app_icon_bytes() -> bytes | None:
    """Read the bundled app icon as bytes for the header logo.

    Returns:
        Parsed raw bytes of docs/assets/icon.svg, or None if unavailable.
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
    _ui_build_start = time.perf_counter()

    page.title = "ywallhaven"
    page.padding = 12
    page.bgcolor = Colors.SURFACE
    # Best-effort native window icon (unsupported on some hosts).
    window_icon = _window_icon_path()
    if window_icon:
        _lg.debug(f"Setting window icon to {window_icon}.")
        page.window.icon = window_icon
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
        except Exception as e:
            _lg.error(f"Failed to apply fallback theme: {e}", exc_info=True)

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
        bus.unsubscribe_all(page)
        page.run_task(slideshow.stop)
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

    async def set_wallpaper(url: str) -> None:
        """Download a wallpaper and set it as the desktop background.

        Supported platforms only (the button is hidden elsewhere).
        The backend keeps the original file when its ratio matches
        the monitor, otherwise downscales; animated images refused.
        Scheduled from the right panel via page.run_task.

        Args:
            url: Full-size wallpaper URL.
        """
        if not is_wallpaper_supported():
            return
        _lg.info(f"Setting wallpaper from {url}.")
        ok, message = await set_wallpaper_from_url(
            middle_panel.api_client.fetch_bytes, url
        )
        _show_snack(page, message, is_error=not ok)

    def on_navigate(delta: int, index: int | None) -> Any:
        """Move to an adjacent wallpaper in the loaded gallery.

        Stays a direct callback on purpose: fullscreen prev/next needs
        the resolved wallpaper back, which fire-and-forget pubsub
        cannot return.

        Args:
            delta: Offset from the current wallpaper.
            index: Current wallpaper index in the cache.

        Returns:
            The resolved wallpaper index.
        """
        return middle_panel.select_relative(delta, index)

    store = FavoritesStore()
    right_panel = RightPanel(on_navigate=on_navigate)
    middle_panel = MiddlePanel(store)
    left_panel = LeftPanel()

    settings_panel = SettingsPanel(theme_picker=theme_picker)

    collections_state = {
        "mode": "gallery",
        "kind": "collection",
        "id": FAVORITES_ID,
    }
    collections_panel = CollectionsPanel(store)

    def _resolve_selection() -> tuple:
        """Return (kind, collection, folder) for the selection.

        Missing targets fall back to the builtin favorites, which
        always exists, so the properties panel never goes empty.
        """
        kind = collections_state["kind"]
        sid = collections_state["id"]
        if kind == "folder":
            folder = next(
                (
                    f
                    for f in store.folders()
                    if f.get("id") == sid
                ),
                None,
            )
            if folder is not None:
                return ("folder", None, folder)
        collection = store.get(sid) or store.get(FAVORITES_ID)
        collections_state["kind"] = "collection"
        collections_state["id"] = collection["id"]
        return ("collection", collection, None)

    def _show_selection() -> None:
        """Render right properties + left settings for selection."""
        kind, collection, folder = _resolve_selection()
        if kind == "folder":
            count = len(store.scan_folder(folder.get("path", "")))
            right_panel.show_collection(
                None, folder=folder, folder_count=count
            )
            collection_settings.load_folder(folder, count)
        else:
            right_panel.show_collection(collection)
            collection_settings.load_collection(collection)

    def _refresh_collections() -> None:
        """Rebuild the grid and re-render the current selection."""
        collections_panel.refresh()
        if collections_state["mode"] == "collections":
            _show_selection()
        page.run_task(_sync_slideshow)

    collection_settings = CollectionSettingsPanel(
        store, on_changed=_refresh_collections
    )

    def _paint_mode_button() -> None:
        """Highlight the heart button in collections mode."""
        active = collections_state["mode"] == "collections"
        mode_button.bgcolor = (
            Colors.PRIMARY_CONTAINER
            if active
            else Colors.SURFACE_CONTAINER_HIGHEST
        )
        try:
            mode_button.update()
        except Exception as e:
            _lg.debug(f"Mode button update deferred: {e}")

    def _set_mode(mode: str) -> None:
        """Swap middle/left content between gallery and collections."""
        collections_state["mode"] = mode
        if mode == "collections":
            middle_wrapped.content = collections_panel
            left_wrapped.content = collection_settings
            _refresh_collections()
        else:
            middle_wrapped.content = middle_panel
            left_wrapped.content = left_panel
            page.run_task(_sync_slideshow)
        _paint_mode_button()
        try:
            middle_wrapped.update()
            left_wrapped.update()
        except Exception as e:
            _lg.debug(f"Mode swap update deferred: {e}")

    def _toggle_mode(e) -> None:
        """Flip gallery ⇄ collections from the heart button."""
        _set_mode(
            "gallery"
            if collections_state["mode"] == "collections"
            else "collections"
        )

    def _on_bus_collection_select(topic: str, message: Any) -> None:
        """Show the collection/folder picked in the grid."""
        payload = message or {}
        kind = payload.get("kind", "collection")
        sid = payload.get("id", "")
        if not sid:
            return
        collections_state["kind"] = kind
        collections_state["id"] = sid
        _show_selection()

    def _open_create_dialog(
        wallpaper: Dict[str, Any] | List[Dict[str, Any]] | None = None,
    ) -> None:
        """Show the new-collection dialog with cover and settings.

        Args:
            wallpaper: Optional wallpaper (or list) to add right
                after creation (coming from the picker).
        """
        name_field = TextField(
            label="Collection name",
            hint_text="My wallpapers",
            filled=True,
        )
        cover_dd = Dropdown(
            label="Cover",
            value="last",
            options=[
                DropdownOption(key=m, text=m)
                for m in ("last", "heart", "icon")
            ],
        )
        icon_dd = Dropdown(
            label="Icon",
            value="IMAGE",
            options=[
                DropdownOption(key=name, text=name)
                for name in ICON_PRESETS
            ],
        )
        interval_field = TextField(
            label="Slideshow interval, seconds",
            value="300",
            filled=True,
        )
        busy = {"value": False}

        def _close(e=None) -> None:
            page.pop_dialog()

        def _create(e) -> None:
            # Guard against double taps: the dialog stays open a
            # frame after the first press, and a second press would
            # create a same-named twin collection.
            if busy["value"]:
                return
            busy["value"] = True
            name = (name_field.value or "").strip()
            if not name:
                name_field.error = "Name is required"
                name_field.update()
                busy["value"] = False
                return
            try:
                interval = int((interval_field.value or "").strip())
            except (ValueError, TypeError):
                interval_field.error = "Invalid number"
                interval_field.update()
                busy["value"] = False
                return
            if interval < 10:
                interval_field.error = "Minimum 10 seconds"
                interval_field.update()
                busy["value"] = False
                return
            cover: Dict[str, Any] = {"mode": cover_dd.value or "last"}
            if cover["mode"] == "icon":
                cover["icon"] = icon_dd.value or "IMAGE"
            created = store.create(
                name, cover=cover, settings={"interval": interval}
            )
            if created is None:
                name_field.error = "Could not create"
                name_field.update()
                busy["value"] = False
                return
            page.pop_dialog()
            pending = (
                [wallpaper]
                if isinstance(wallpaper, dict)
                else list(wallpaper or [])
            )
            for item in pending:
                if item.get("id"):
                    store.add(created["id"], item)
            collections_state["kind"] = "collection"
            collections_state["id"] = created["id"]
            # Close the creation dialog and, when launched from the
            # add-to-collection picker, the picker underneath too.
            page.pop_dialog()
            _refresh_collections()

        page.show_dialog(
            AlertDialog(
                modal=True,
                title=Text("New collection"),
                content=Column(
                    tight=True,
                    spacing=8,
                    controls=[
                        name_field,
                        cover_dd,
                        icon_dd,
                        interval_field,
                    ],
                ),
                actions=[
                    TextButton("Cancel", on_click=_close),
                    FilledButton(
                        content="Create",
                        icon=Icons.ADD,
                        on_click=_create,
                    ),
                ],
            )
        )

    def _confirm_collection_action(
        action: str, sid: str, title: str, question: str
    ) -> None:
        """Confirm destructive collection actions (delete/clear)."""

        def _close(e=None) -> None:
            page.pop_dialog()

        def _apply(e) -> None:
            page.pop_dialog()
            if action == "delete":
                store.delete(sid)
            else:
                store.clear(sid)
            _refresh_collections()

        page.show_dialog(
            AlertDialog(
                modal=True,
                title=Text(title),
                content=Text(question),
                actions=[
                    TextButton("Cancel", on_click=_close),
                    FilledButton(content="Confirm", on_click=_apply),
                ],
            )
        )

    def _on_bus_collection_create(topic: str, message: Any) -> None:
        """Open the creation dialog from the create tile."""
        _open_create_dialog()

    def _on_bus_collection_delete(topic: str, message: Any) -> None:
        """Confirm and delete a user collection."""
        sid = (message or {}).get("id", "")
        target = store.get(sid)
        if target is None or target.get("builtin", False):
            return
        _confirm_collection_action(
            "delete",
            sid,
            "Delete collection?",
            f"'{target.get('name', '')}' will be removed. "
            "Downloaded files are not affected.",
        )

    def _on_bus_collection_clear(topic: str, message: Any) -> None:
        """Confirm and empty a collection."""
        sid = (message or {}).get("id", "")
        target = store.get(sid)
        if target is None:
            return
        _confirm_collection_action(
            "clear",
            sid,
            "Clear collection?",
            f"All wallpapers will be removed from "
            f"'{target.get('name', '')}'.",
        )

    async def _apply_slideshow_wallpaper(
        wallpaper: Dict[str, Any],
    ) -> bool:
        """Apply one slideshow wallpaper via the shared installer."""
        url = str(wallpaper.get("path", ""))
        if not url:
            return False
        if url.startswith("http"):
            fetch = middle_panel.api_client.fetch_bytes
        else:

            async def fetch(_url: str) -> bytes | None:
                def _read() -> bytes | None:
                    try:
                        return Path(_url).read_bytes()
                    except OSError:
                        return None

                return await asyncio.to_thread(_read)

        ok, _message = await set_wallpaper_from_url(fetch, url)
        return ok

    slideshow = SlideshowService(
        _apply_slideshow_wallpaper,
        paused=right_panel.is_fullscreen_open,
    )

    async def _sync_slideshow() -> None:
        """Align the engine with the selected collection settings."""
        if collections_state["mode"] != "collections":
            await slideshow.stop()
            return
        kind, collection, folder = _resolve_selection()
        if kind == "folder":
            settings = folder.get("settings") or {}
            walls = store.scan_folder(folder.get("path", ""))
            label = folder.get("name", "?")
        else:
            settings = collection.get("settings") or {}
            walls = collection.get("wallpapers") or []
            label = collection.get("name", "?")
        if settings.get("slideshow") and walls:
            await slideshow.start(
                walls,
                label=label,
                interval=settings.get("interval", 300),
                order=settings.get("order", "sequential"),
            )
        else:
            await slideshow.stop()

    def _resolve_download_items(
        kind: str, sid: str
    ) -> tuple[str, List[Dict[str, Any]]]:
        """Return (name, wallpapers) for a collection or folder."""
        if kind == "folder":
            folder = next(
                (f for f in store.folders() if f.get("id") == sid),
                None,
            )
            if folder is None:
                return "", []
            return (
                folder.get("name", "folder"),
                store.scan_folder(folder.get("path", "")),
            )
        collection = store.get(sid)
        if collection is None:
            return "", []
        return (
            collection.get("name", "collection"),
            list(collection.get("wallpapers") or []),
        )

    def _open_collection_download(kind: str, sid: str) -> None:
        """Show the download-all dialog with ZIP/folder choice."""
        name, walls = _resolve_download_items(kind, sid)
        if not walls:
            _show_snack(page, "Nothing to download", is_error=True)
            return
        _open_download_dialog(name, walls)

    def _open_download_dialog(
        name: str, walls: List[Dict[str, Any]]
    ) -> None:
        """Show the download dialog for an explicit wallpaper list."""
        from flet import ProgressBar

        status = Text(f"0/{len(walls)} files")
        bar = ProgressBar(value=0)

        def _close(e=None) -> None:
            page.pop_dialog()

        def _progress(done: int, total: int) -> None:
            status.value = f"{done}/{total} files"
            bar.value = done / total if total else 0
            try:
                status.update()
                bar.update()
            except Exception as e:
                _lg.debug(f"Download progress deferred: {e}")

        async def _download_zip(e=None) -> None:
            data, failed = await build_zip(
                walls,
                middle_panel.api_client.fetch_bytes,
                progress=_progress,
            )
            if data is None:
                _show_snack(page, "Download failed", is_error=True)
                page.pop_dialog()
                return
            saved = await file_picker.save_file(
                dialog_title="Save collection",
                file_name=f"{name}.zip",
                file_type=FilePickerFileType.CUSTOM,
                allowed_extensions=["zip"],
                src_bytes=data,
            )
            page.pop_dialog()
            if saved:
                _show_snack(page, "Collection downloaded")
            else:
                _show_snack(page, "Save cancelled")

        async def _download_folder(e=None) -> None:
            directory = await file_picker.get_directory_path(
                dialog_title="Choose folder",
            )
            if not directory:
                return
            taken: set = set()
            failed = 0
            total = len(walls)
            for position, wallpaper in enumerate(walls):
                data = await resolve_bytes(
                    wallpaper, middle_panel.api_client.fetch_bytes
                )
                _progress(position + 1, total)
                if not data:
                    failed += 1
                    continue
                target = (
                    Path(directory)
                    / unique_name(
                        taken, display_name(wallpaper, position)
                    )
                )

                def _write() -> bool:
                    try:
                        target.write_bytes(data)
                    except OSError:
                        return False
                    return True

                if not await asyncio.to_thread(_write):
                    failed += 1
            page.pop_dialog()
            if failed:
                _show_snack(
                    page,
                    f"Downloaded {total - failed}/{total}",
                    is_error=True,
                )
            else:
                _show_snack(page, "Collection downloaded")

        def _run_zip(e) -> None:
            page.run_task(_download_zip)

        def _run_folder(e) -> None:
            page.run_task(_download_folder)

        page.show_dialog(
            AlertDialog(
                modal=True,
                title=Text(f"Download '{name}'"),
                content=Column(
                    tight=True,
                    spacing=8,
                    controls=[status, bar],
                ),
                actions=[
                    TextButton("Cancel", on_click=_close),
                    FilledButton(
                        content="ZIP file", on_click=_run_zip
                    ),
                    FilledButton(
                        content="Folder", on_click=_run_folder
                    ),
                ],
            )
        )

    def _selected_wallpapers(
        kind: str, sid: str, ids: List[str]
    ) -> tuple[str, List[Dict[str, Any]]]:
        """Resolve checked ids to (name, wallpapers) for actions."""
        if kind == "folder":
            folder = next(
                (f for f in store.folders() if f.get("id") == sid),
                None,
            )
            if folder is None:
                return "", []
            scanned = {
                str(w.get("id", "")): w
                for w in store.scan_folder(folder.get("path", ""))
            }
            walls = [scanned[i] for i in ids if i in scanned]
            return folder.get("name", "folder"), walls
        collection = store.get(sid)
        if collection is None:
            return "", []
        by_id = {
            str(w.get("id", "")): w
            for w in collection.get("wallpapers") or []
        }
        walls = [by_id[i] for i in ids if i in by_id]
        return collection.get("name", "collection"), walls

    def _on_bus_collection_remove_one(topic: str, message: Any) -> None:
        """Remove one wallpaper from a collection (no confirm)."""
        payload = message or {}
        if payload.get("kind") != "collection":
            return
        sid = payload.get("id", "")
        wid = payload.get("wallpaper_id", "")
        if sid and wid and store.remove(sid, wid):
            _show_snack(page, "Removed from collection")
            bus.publish(page, bus.TOPIC_FAVORITES, {})
            _refresh_collections()

    def _on_bus_collection_delete_selected(
        topic: str, message: Any
    ) -> None:
        """Confirm and delete checked wallpapers."""
        payload = message or {}
        if payload.get("kind") != "collection":
            return
        sid = payload.get("id", "")
        ids = payload.get("wallpaper_ids") or []
        if not sid or not ids:
            return
        collection = store.get(sid)
        if collection is None:
            return

        def _close(e=None) -> None:
            page.pop_dialog()

        def _apply(e) -> None:
            page.pop_dialog()
            for wid in ids:
                store.remove(sid, wid)
            # Checked positions now point at surviving wallpapers;
            # stale checks would remove the wrong set next time.
            collections_panel.exit_selection()
            _show_snack(page, f"Removed {len(ids)}")
            bus.publish(page, bus.TOPIC_FAVORITES, {})
            _refresh_collections()

        page.show_dialog(
            AlertDialog(
                modal=True,
                title=Text("Delete selected?"),
                content=Text(
                    f"{len(ids)} wallpapers will be removed from "
                    f"'{collection.get('name', '')}'."
                ),
                actions=[
                    TextButton("Cancel", on_click=_close),
                    FilledButton(content="Delete", on_click=_apply),
                ],
            )
        )

    def _on_bus_collection_download_selected(
        topic: str, message: Any
    ) -> None:
        """Download checked wallpapers through the dialog."""
        payload = message or {}
        name, walls = _selected_wallpapers(
            payload.get("kind", "collection"),
            payload.get("id", ""),
            payload.get("wallpaper_ids") or [],
        )
        if not walls:
            _show_snack(page, "Nothing to download", is_error=True)
            return
        _open_download_dialog(f"{name} selection", walls)

    def _on_bus_collection_move_selected(
        topic: str, message: Any
    ) -> None:
        """Add checked wallpapers to another collection."""
        payload = message or {}
        _name, walls = _selected_wallpapers(
            payload.get("kind", "collection"),
            payload.get("id", ""),
            payload.get("wallpaper_ids") or [],
        )
        if walls:
            _open_pick_dialog_list(walls)
            # The checked set did its job (resolved into the picker);
            # clear it now so cancel does not leave stale checks.
            collections_panel.exit_selection()

    def _on_bus_slideshow_selection(topic: str, message: Any) -> None:
        """Run the slideshow from checked wallpapers."""
        payload = message or {}
        kind = payload.get("kind", "collection")
        sid = payload.get("id", "")
        _name, walls = _selected_wallpapers(
            kind, sid, payload.get("wallpaper_ids") or []
        )
        if not walls:
            return

        async def _run() -> None:
            if kind == "folder":
                folder = next(
                    (
                        f
                        for f in store.folders()
                        if f.get("id") == sid
                    ),
                    None,
                )
                interval = ((folder or {}).get("settings") or {}).get(
                    "interval", 300
                )
            else:
                collection = store.get(sid) or {}
                interval = (collection.get("settings") or {}).get(
                    "interval", 300
                )
            await slideshow.start(
                walls,
                label="Selection",
                interval=interval,
                order="sequential",
            )
            _show_snack(page, "Slideshow from selection")

        page.run_task(_run)

    def _on_bus_collection_download(topic: str, message: Any) -> None:
        """Open the download dialog for a collection/folder."""
        payload = message or {}
        _open_collection_download(
            payload.get("kind", "collection"), payload.get("id", "")
        )

    def _on_bus_favorite_toggle(topic: str, message: Any) -> None:
        """Toggle a wallpaper in the builtin favorites."""
        wallpaper = (message or {}).get("wallpaper")
        if not isinstance(wallpaper, dict):
            return
        wid = str(wallpaper.get("id", ""))
        if not wid:
            return
        if store.contains(FAVORITES_ID, wid):
            store.remove(FAVORITES_ID, wid)
            _show_snack(page, "Removed from favorites")
        else:
            store.add(FAVORITES_ID, wallpaper)
            _show_snack(page, "Added to favorites")
        bus.publish(page, bus.TOPIC_FAVORITES, {})

    def _on_bus_collection_pick(topic: str, message: Any) -> None:
        """Open the add-to-collection picker for a wallpaper."""
        wallpaper = (message or {}).get("wallpaper")
        if isinstance(wallpaper, dict) and wallpaper.get("id"):
            _open_pick_dialog(wallpaper)

    def _open_pick_dialog(wallpaper: Dict[str, Any]) -> None:
        """Show the collection picker for one wallpaper."""
        _open_pick_dialog_list([wallpaper])

    def _open_pick_dialog_list(wallpapers: List[Dict[str, Any]]) -> None:
        """Show the collection picker adding every wallpaper."""
        wallpapers = [w for w in wallpapers if w.get("id")]
        if not wallpapers:
            return

        def _close(e=None) -> None:
            page.pop_dialog()

        def _choose(collection_id: str) -> Callable:
            def _add(e) -> None:
                page.pop_dialog()
                added = sum(
                    1
                    for wallpaper in wallpapers
                    if store.add(collection_id, wallpaper)
                )
                total = len(wallpapers)
                if added == total:
                    _show_snack(page, "Added to collection")
                elif added:
                    _show_snack(
                        page, f"Added {added}/{total} (rest dupes)"
                    )
                else:
                    _show_snack(page, "Already in collection")
                bus.publish(page, bus.TOPIC_FAVORITES, {})

            return _add

        # For a single wallpaper, rows of collections already holding
        # it get a check and stay disabled (no duplicate add). For a
        # multi-paste (move selected), partial hits stay enabled.
        contains: set[str] = set()
        if len(wallpapers) == 1:
            contains = set(
                store.collections_containing(
                    str(wallpapers[0].get("id", ""))
                )
            )

        rows: List[Any] = []
        for collection in store.collections():
            count = len(collection.get("wallpapers") or [])
            marker = "♥ " if collection["id"] == FAVORITES_ID else ""
            already = collection["id"] in contains
            if already:
                marker = f"{marker}✓ "
            rows.append(
                TextButton(
                    content=f"{marker}{collection.get('name', '?')} "
                    f"({count})",
                    disabled=already,
                    on_click=_choose(collection["id"]),
                )
            )
        rows.append(
            TextButton(
                content="+ New collection",
                # Stacked above the picker on purpose: cancelling
                # the creation dialog returns to the picker.
                on_click=lambda e: _open_create_dialog(wallpapers),
            )
        )
        page.show_dialog(
            AlertDialog(
                modal=True,
                title=Text("Add to collection"),
                content=Column(
                    tight=True,
                    spacing=4,
                    controls=rows,
                ),
                actions=[
                    TextButton("Cancel", on_click=_close),
                ],
            )
        )

    def _on_bus_download(topic: str, message: Any) -> None:
        """Start the save flow for a download published on the bus.

        Args:
            topic: Bus topic (always TOPIC_DOWNLOAD here).
            message: {"url": str, "file_name": str, "size": ...} payload.
        """
        payload = message or {}
        request_save(
            payload.get("url", ""),
            payload.get("file_name", "wallpaper"),
            payload.get("size"),
        )

    def _on_bus_wallpaper(topic: str, message: Any) -> None:
        """Set the desktop background for a bus wallpaper request.

        Args:
            topic: Bus topic (always TOPIC_SET_WALLPAPER here).
            message: {"url": str} payload.
        """
        url = (message or {}).get("url", "")
        if url:
            page.run_task(set_wallpaper, url)

    bus.subscribe(page, bus.TOPIC_DOWNLOAD, _on_bus_download)
    bus.subscribe(page, bus.TOPIC_SET_WALLPAPER, _on_bus_wallpaper)
    bus.subscribe(
        page, bus.TOPIC_COLLECTION_SELECT, _on_bus_collection_select
    )
    bus.subscribe(
        page, bus.TOPIC_COLLECTION_CREATE, _on_bus_collection_create
    )
    bus.subscribe(
        page, bus.TOPIC_COLLECTION_DELETE, _on_bus_collection_delete
    )
    bus.subscribe(
        page, bus.TOPIC_COLLECTION_CLEAR, _on_bus_collection_clear
    )
    bus.subscribe(
        page, bus.TOPIC_FAVORITE_TOGGLE, _on_bus_favorite_toggle
    )
    bus.subscribe(
        page, bus.TOPIC_COLLECTION_PICK, _on_bus_collection_pick
    )
    bus.subscribe(
        page, bus.TOPIC_COLLECTION_DOWNLOAD, _on_bus_collection_download
    )
    bus.subscribe(
        page,
        bus.TOPIC_COLLECTION_REMOVE_ONE,
        _on_bus_collection_remove_one,
    )
    bus.subscribe(
        page,
        bus.TOPIC_COLLECTION_DELETE_SELECTED,
        _on_bus_collection_delete_selected,
    )
    bus.subscribe(
        page,
        bus.TOPIC_COLLECTION_DOWNLOAD_SELECTED,
        _on_bus_collection_download_selected,
    )
    bus.subscribe(
        page,
        bus.TOPIC_COLLECTION_MOVE_SELECTED,
        _on_bus_collection_move_selected,
    )
    bus.subscribe(
        page, bus.TOPIC_SLIDESHOW_SELECTION, _on_bus_slideshow_selection
    )

    icon_bytes = _app_icon_bytes()
    logo = (
        Image(src=icon_bytes, width=32, height=32)
        if icon_bytes is not None
        else Icon(Icons.WALLPAPER, size=26)
    )
    current_theme = get_theme(config.data.THEME)
    theme_label = current_theme.name if current_theme else config.data.THEME
    theme_chip = Text(
        theme_label,
        size=11,
        weight="w500",
        color=Colors.ON_SURFACE_VARIANT,
    )
    # Pinned for live updates after Save in settings (theme chip).
    page._ywallhaven_theme_label = theme_chip

    mode_button = IconButton(
        icon=Icons.FAVORITE,
        icon_size=22,
        tooltip="Collections",
        style=None,
        bgcolor=Colors.SURFACE_CONTAINER_HIGHEST,
        on_click=_toggle_mode,
    )

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
                    content=theme_chip,
                ),
                Container(expand=True, content=Text("")),
                mode_button,
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
        except Exception as e:
            _lg.debug(f"Resize handling failed: {e}", exc_info=True)

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

    _lg.debug(
        f"UI assembled in "
        f"{(time.perf_counter() - _ui_build_start) * 1000:.0f} ms."
    )
    _lg.info(
        f"UI ready: theme={config.data.THEME}, "
        f"check_updates={config.data.CHECK_UPDATES}."
    )

    if config.data.CHECK_UPDATES:
        page.run_task(check_and_offer, page, manual=False)