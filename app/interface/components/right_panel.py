"""Right panel: preview and properties of the selected wallpaper."""

import os
from typing import Any, Callable, Dict, List

from flet import (
    AlertDialog,
    Alignment,
    Blur,
    BoxFit,
    ClipBehavior,
    Colors,
    Column,
    Container,
    CrossAxisAlignment,
    FilledButton,
    FilledTonalButton,
    GestureDetector,
    IconButton,
    Icons,
    Image,
    ListView,
    MainAxisAlignment,
    Padding,
    Row,
    Stack,
    Text,
    TextButton,
    UrlTarget,
)
from app.core import get_logger
from app.core.resources import register
from app.service import WallhavenAPI

_lg = get_logger()


class RightPanel(Container):
    """Preview and properties panel for the selected wallpaper."""

    PREVIEW_RADIUS = 12
    GAP = 12
    TAG_CHIP_LIMIT = 10
    PRESET_RESOLUTIONS = [
        (1920, 1080),
        (2560, 1440),
        (3440, 1440),
        (3840, 2160),
    ]

    def __init__(
        self,
        on_download: Callable[[str, str, tuple[int, int] | None], None],
        on_tag_click: Callable[[str], None] | None = None,
        on_navigate: Callable[[int, int | None], Any] | None = None,
    ) -> None:
        super().__init__()
        self._on_download = on_download
        self._on_tag_click = on_tag_click
        self._on_navigate = on_navigate
        self._api_client = WallhavenAPI()
        register(self._api_client.close)
        self.expand = 1
        self.padding = 12
        self.bgcolor = Colors.DEEP_PURPLE_500
        self.alignment = Alignment.CENTER
        self.content = self._build_empty_state()
        self._last_wallpaper: Dict[str, Any] | None = None
        self._current_index: int | None = None
        self._fullscreen_layer: Container | None = None
        self._fullscreen_image: Image | None = None
        self._backdrop_image: Image | None = None
        self._tags_fetch_generation = 0
        self._tags_expanded = False

    def did_mount(self) -> None:
        """Create and mount the fullscreen layer above the page."""
        super().did_mount()
        self._build_fullscreen_layer()
        self.page.overlay.append(self._fullscreen_layer)

    def will_unmount(self) -> None:
        """Remove the fullscreen layer from the page overlay."""
        super().will_unmount()
        if (
            self._fullscreen_layer is not None
            and self._fullscreen_layer in self.page.overlay
        ):
            self.page.overlay.remove(self._fullscreen_layer)
        self.page.run_task(self._api_client.close)

    # Public API ----------------------------------------------------

    def update_preview(
        self, wallpaper: Dict[str, Any], index: int | None = None
    ) -> None:
        """Show the preview and properties of a wallpaper.

        Args:
            wallpaper: Wallpaper dict from the Wallhaven API.
            index: Index of the wallpaper in the loaded grid cache.
        """
        self._last_wallpaper = wallpaper
        self._tags_expanded = False
        if index is not None:
            self._current_index = index

        if (
            self._fullscreen_layer is not None
            and self._fullscreen_layer.visible
        ):
            self._refresh_fullscreen_image()

        self.content = Column(
            expand=True,
            spacing=self.GAP,
            controls=[
                self._build_preview(wallpaper),
                self._build_properties_view(wallpaper),
                self._build_download_button(),
            ],
        )
        self.update()

        self.page.run_task(self._load_tags, wallpaper)

    async def _load_tags(self, wallpaper: Dict[str, Any]) -> None:
        """Fetch and render the clickable tags of a wallpaper.

        The search endpoint omits tags, so the wallpaper detail is
        fetched separately and the tag chips are rendered once known.

        Args:
            wallpaper: Wallpaper dict from the search results.
        """
        wallpaper_id = wallpaper.get("id")
        if not wallpaper_id or wallpaper.get("tags"):
            return

        generation = self._tags_fetch_generation + 1
        self._tags_fetch_generation = generation
        try:
            detail = await self._api_client.get_wallpaper(wallpaper_id)
        except Exception:
            return

        if generation != self._tags_fetch_generation:
            return
        if wallpaper is not self._last_wallpaper:
            return

        tags = (detail or {}).get("tags")
        if not tags:
            return

        wallpaper["tags"] = tags
        self.content = Column(
            expand=True,
            spacing=self.GAP,
            controls=[
                self._build_preview(wallpaper),
                self._build_properties_view(wallpaper),
                self._build_download_button(),
            ],
        )
        self.update()

    def _build_download_button(self) -> FilledButton:
        """Build the download button shown below the properties."""
        return FilledButton(
            content="Download",
            icon=Icons.DOWNLOAD,
            on_click=self._handle_download_click,
        )

    def _handle_download_click(self, e) -> None:
        """Open the resolution chooser for the current wallpaper.

        Args:
            e: Click event from the download button.
        """
        self.request_download(self._last_wallpaper)

    def request_download(
        self, wallpaper: Dict[str, Any] | None
    ) -> None:
        """Show the resolution chooser for the given wallpaper.

        Args:
            wallpaper: Wallpaper dict from the search results.
        """
        if wallpaper is None or self._on_download is None:
            return

        self._last_wallpaper = wallpaper
        self._show_resolution_dialog(wallpaper)

    def _show_resolution_dialog(self, wallpaper: Dict[str, Any]) -> None:
        """Show the resolution chooser dialog for a wallpaper.

        When the search response lacks the wallpaper dimensions, the
        detail endpoint is polled in the background and the dialog is
        refreshed with the resolution presets once they are known.

        Args:
            wallpaper: Wallpaper dict from the search results.
        """
        width = int(wallpaper.get("dimension_x") or 0)
        height = int(wallpaper.get("dimension_y") or 0)

        base, ext = self._file_parts(wallpaper)
        controls: List[Any] = [
            self._resolution_option("Original", None, base, ext),
        ]
        if width and height:
            controls.extend(
                self._resolution_option(f"{w}x{h}", (w, h), base, ext)
                for w, h in self.PRESET_RESOLUTIONS
                if w <= width and h <= height
            )

        dialog = AlertDialog(
            modal=True,
            title=Text("Download wallpaper"),
            actions_alignment=MainAxisAlignment.CENTER,
            actions=[
                TextButton("Cancel", on_click=self._close_dialog),
            ],
            content=Column(
                tight=True,
                spacing=8,
                controls=controls,
            ),
        )
        self._dialog = dialog
        self.page.show_dialog(dialog)

        if not width or not height:
            self.page.run_task(
                self._load_resolution_details, wallpaper, dialog
            )

    async def _load_resolution_details(
        self, wallpaper: Dict[str, Any], dialog: AlertDialog
    ) -> None:
        """Fetch the missing wallpaper dimensions and refresh the dialog.

        Args:
            wallpaper: Wallpaper dict from the search results.
            dialog: The open resolution chooser to refresh.
        """
        detail = await self._api_client.get_wallpaper(
            str(wallpaper.get("id", ""))
        )
        if not detail:
            return

        if dialog is not self._dialog or not dialog.open:
            return

        width = int(detail.get("dimension_x") or 0)
        height = int(detail.get("dimension_y") or 0)
        if not width or not height:
            return

        wallpaper["dimension_x"] = width
        wallpaper["dimension_y"] = height
        base, ext = self._file_parts(wallpaper)
        dialog.content = Column(
            tight=True,
            spacing=8,
            controls=[
                self._resolution_option("Original", None, base, ext),
                *(
                    self._resolution_option(f"{w}x{h}", (w, h), base, ext)
                    for w, h in self.PRESET_RESOLUTIONS
                    if w <= width and h <= height
                ),
            ],
        )
        dialog.update()

    def _file_parts(
        self, wallpaper: Dict[str, Any]
    ) -> tuple[str, str]:
        """Split the wallpaper file name into base and extension.

        Args:
            wallpaper: Wallpaper dict from the search results.

        Returns:
            Tuple of the base name and the extension with the dot.
        """
        file_name = WallhavenAPI.build_filename(wallpaper)
        return os.path.splitext(file_name)

    def _close_dialog(self, e) -> None:
        """Close the resolution chooser dialog without downloading.

        Args:
            e: Click event from the cancel button.
        """
        self._dialog.open = False
        self._dialog.update()

    def _resolution_option(
        self,
        label: str,
        size: tuple[int, int] | None,
        base: str,
        ext: str,
    ) -> FilledButton:
        """Build a resolution option button for the download dialog.

        Args:
            label: Human-readable resolution label.
            size: Requested pixel size, or None for the original file.
            base: File name without extension.
            ext: Original file extension (with the leading dot).

        Returns:
            Button that triggers the download in the given resolution.
        """
        file_name = f"{base}{ext}" if size is None else f"{base}-{label}.jpg"

        def choose(e, size=size, file_name=file_name) -> None:
            self._dialog.open = False
            self._dialog.update()
            self._on_download(
                self._last_wallpaper.get("path", ""), file_name, size
            )

        return FilledButton(
            content=label,
            width=240,
            height=38,
            on_click=choose,
        )

    # Private builders ----------------------------------------------

    def _build_empty_state(self) -> Container:
        """Build the placeholder shown when nothing is selected."""
        return Container(
            alignment=Alignment.CENTER,
            content=Text(
                "Select a wallpaper",
                color=Colors.WHITE70,
            ),
        )

    def _build_preview(self, wallpaper: Dict[str, Any]) -> Container:
        """Build the rounded preview container for a wallpaper.

        Args:
            wallpaper: Wallpaper dict from the Wallhaven API.

        Returns:
            Rounded container with the full-size image.
        """
        return Container(
            expand=True,
            border_radius=self.PREVIEW_RADIUS,
            clip_behavior=ClipBehavior.HARD_EDGE,
            bgcolor=Colors.SURFACE_DIM,
            on_click=self.open_fullscreen,
            content=Image(
                src=wallpaper.get("path"),
                fit=BoxFit.COVER,
                expand=True,
            ),
        )

    def _build_fullscreen_layer(self) -> Container:
        """Build the modernized fullscreen overlay shown on preview click.

        The wallpaper is centered with generous window margins, the area
        behind it is blurred and dimmed to remove black bars, and the
        previous / close / next buttons are placed in a centered row
        below the image.

        Returns:
            Fullscreen container with the wallpaper image.
        """
        self._fullscreen_image = Image(
            src="",
            fit=BoxFit.CONTAIN,
            expand=True,
        )

        self._backdrop_image = Image(
            src="",
            fit=BoxFit.COVER,
            expand=True,
        )

        self._backdrop = Container(
            expand=True,
            clip_behavior=ClipBehavior.HARD_EDGE,
            content=self._backdrop_image,
        )

        self._fullscreen_layer = Container(
            visible=False,
            expand=True,
            content=Stack(
                expand=True,
                controls=[
                    self._backdrop,
                    Container(
                        expand=True,
                        bgcolor=Colors.BLACK54,
                        blur=Blur(24, 24),
                    ),
                    Column(
                        expand=True,
                        horizontal_alignment=CrossAxisAlignment.CENTER,
                        controls=[
                            Container(
                                expand=True,
                                padding=Padding(
                                    top=36, right=36, bottom=14, left=36
                                ),
                                alignment=Alignment.CENTER,
                                on_click=self.close_fullscreen,
                                content=self._fullscreen_image,
                            ),
                            Row(
                                spacing=12,
                                alignment=MainAxisAlignment.CENTER,
                                controls=[
                                    self._nav_button(
                                        Icons.CHEVRON_LEFT,
                                        self._go_previous,
                                    ),
                                    self._nav_button(
                                        Icons.CLOSE,
                                        self.close_fullscreen,
                                    ),
                                    self._nav_button(
                                        Icons.CHEVRON_RIGHT,
                                        self._go_next,
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        )

        return self._fullscreen_layer

    def _nav_button(self, icon: Any, handler) -> IconButton:
        """Build a fullscreen navigation button.

        Args:
            icon: Icon to show on the button.
            handler: Click handler for the button.

        Returns:
            Rounded half-transparent navigation button.
        """
        return IconButton(
            icon=icon,
            icon_color=Colors.WHITE,
            icon_size=40,
            padding=10,
            bgcolor=Colors.BLACK26,
            on_click=handler,
        )

    def _refresh_fullscreen_image(self) -> None:
        """Update the fullscreen image and its blurred backdrop.

        The backdrop reuses the full-size source so both layers stay
        in sync and no half-blurred thumbnail shows up at the edges.
        """
        if self._last_wallpaper is None or self._fullscreen_layer is None:
            return

        src = self._last_wallpaper.get("path")
        self._fullscreen_image.src = src
        self._backdrop_image.src = src

    def open_fullscreen(self, e) -> None:
        """Show the current wallpaper image in fullscreen.

        Args:
            e: Click event from the preview container.
        """
        if self._last_wallpaper is None or self._fullscreen_layer is None:
            return

        _lg.debug(f"Fullscreen opened for {self._last_wallpaper.get('id')}.")
        self._refresh_fullscreen_image()
        self._fullscreen_layer.visible = True
        self._fullscreen_layer.update()

    def close_fullscreen(self, e) -> None:
        """Hide the fullscreen overlay.

        Args:
            e: Click event from the fullscreen layer.
        """
        if self._fullscreen_layer is None:
            return

        _lg.debug("Fullscreen closed.")
        self._fullscreen_layer.visible = False
        self._fullscreen_layer.update()

    def _go_previous(self, e) -> None:
        """Show the previous wallpaper in fullscreen.

        Args:
            e: Click event from the previous button.
        """
        self.page.run_task(self._navigate, -1)

    def _go_next(self, e) -> None:
        """Show the next wallpaper in fullscreen.

        Args:
            e: Click event from the next button.
        """
        self.page.run_task(self._navigate, 1)

    async def _navigate(self, delta: int) -> None:
        """Move to an adjacent wallpaper and refresh the fullscreen view.

        Args:
            delta: Direction and step of the navigation.
        """
        if self._on_navigate is None:
            return

        _lg.debug(f"Fullscreen navigate: delta={delta}.")
        result = await self._on_navigate(delta, self._current_index)
        if not result:
            return

        index, wallpaper = result
        if index == self._current_index:
            return

        self.update_preview(wallpaper, index)
        if self._fullscreen_layer is not None:
            self._fullscreen_layer.update()

    def _build_properties_view(self, wallpaper: Dict[str, Any]) -> ListView:
        """Build a scrollable properties list for the right panel.

        The properties and tags are placed in a scrollable list so the
        download button stays pinned at the bottom of the panel.

        Args:
            wallpaper: Wallpaper dict from the API.

        Returns:
            Scrollable list view with all the property rows.
        """
        return ListView(
            expand=True,
            spacing=6,
            controls=[c for c in self._build_properties(wallpaper)],
        )

    def _build_properties(self, wallpaper: Dict[str, Any]) -> List[Any]:
        """Build the properties controls from a wallpaper dict.

        Args:
            wallpaper: Wallpaper dict from the Wallhaven API.

        Returns:
            List with property rows, colors, tags and links.
        """
        rows = [
            self._make_row("Resolution", wallpaper.get("resolution")),
            self._make_row("Aspect ratio", wallpaper.get("ratio")),
            self._make_row(
                "File size",
                self._format_size(wallpaper.get("file_size")),
            ),
            self._make_row("Type", wallpaper.get("file_type")),
            self._make_row("Category", wallpaper.get("category")),
            self._make_row("Purity", wallpaper.get("purity")),
            self._make_row("Views", wallpaper.get("views")),
            self._make_row("Favorites", wallpaper.get("favorites")),
            self._make_row("Added", wallpaper.get("created_at")),
        ]

        controls: List[Any] = [row for row in rows if row is not None]
        controls.append(self._make_colors_row(wallpaper.get("colors")))
        controls.append(self._make_tags_row(wallpaper.get("tags")))
        controls.append(self._make_links_row(wallpaper))

        return [c for c in controls if c is not None]

    @staticmethod
    def _make_row(label: str, value: Any) -> Row | None:
        """Build a single label/value row.

        Args:
            label: Property label.
            value: Property value.

        Returns:
            Row with label and value, or None if the value is missing.
        """
        if value is None or value == "":
            return None

        return Row(
            spacing=8,
            controls=[
                Text(
                    label,
                    width=110,
                    size=12,
                    color=Colors.WHITE70,
                ),
                Text(
                    str(value),
                    size=12,
                    selectable=True,
                    expand=True,
                ),
            ],
        )

    @staticmethod
    def _format_size(size: Any) -> str | None:
        """Format a file size in bytes as a human-readable string.

        Args:
            size: File size in bytes.

        Returns:
            Formatted size in MB, or None if the size is missing.
        """
        if size is None:
            return None

        return f"{int(size) / (1024 * 1024):.2f} MB"

    @staticmethod
    def _make_colors_row(colors: Any) -> Row | None:
        """Build a row of color dots.

        Args:
            colors: List of hex color strings.

        Returns:
            Wrapped row with color dots, or None if no colors are present.
        """
        if not colors:
            return None

        return Row(
            wrap=True,
            spacing=6,
            run_spacing=6,
            controls=[
                Container(
                    width=18,
                    height=18,
                    border_radius=9,
                    bgcolor=color,
                )
                for color in colors
            ],
        )

    def _make_tags_row(self, tags: Any) -> Row | None:
        """Build a row of clickable tag chips.

        When there are more tags than :attr:`TAG_CHIP_LIMIT`, only the
        first chips are rendered together with a "+N more" button that
        reveals the rest (see :meth:`_expand_tags`).

        Args:
            tags: List of tag dicts from the API.

        Returns:
            Wrapped row with tag chips, or None if no tags are present.
        """
        if not tags:
            return None

        visible_tags = (
            list(tags)
            if self._tags_expanded
            else list(tags)[: self.TAG_CHIP_LIMIT]
        )
        hidden_count = len(tags) - len(visible_tags)

        chips = [
            GestureDetector(
                on_tap=self._make_tag_handler(tag),
                content=Container(
                    padding=6,
                    border_radius=6,
                    bgcolor=Colors.GREY_800,
                    content=Text(
                        tag.get("name", ""),
                        size=11,
                    ),
                ),
            )
            for tag in visible_tags
        ]

        if hidden_count > 0:
            chips.append(
                TextButton(
                    content=f"+{hidden_count} more",
                    on_click=self._expand_tags,
                )
            )

        return Row(
            wrap=True,
            spacing=6,
            run_spacing=6,
            controls=chips,
        )

    def _make_tag_handler(self, tag: Dict[str, Any]) -> Callable:
        """Return an async-safe tap handler for a single tag chip.

        Args:
            tag: Tag dict from the API.

        Returns:
            Click handler that opens the tag search.
        """
        name = tag.get("name", "")

        def handler(e) -> None:
            self._open_tag(name)

        return handler

    def _open_tag(self, name: str) -> None:
        """Run a search for the given tag.

        Args:
            name: Tag name to search for.
        """
        if name and self._on_tag_click:
            self._on_tag_click(name)

    def _expand_tags(self, e) -> None:
        """Show the full list of tag chips for the current wallpaper.

        Args:
            e: Click event from the "+N more" button.
        """
        if self._last_wallpaper is None:
            return

        self._tags_expanded = True
        self.content = Column(
            expand=True,
            spacing=self.GAP,
            controls=[
                self._build_preview(self._last_wallpaper),
                self._build_properties_view(self._last_wallpaper),
                self._build_download_button(),
            ],
        )
        self.update()

    def _make_links_row(self, wallpaper: Dict[str, Any]) -> Row | None:
        """Build compact buttons for a wallpaper links.

        Args:
            wallpaper: Wallpaper dict from the Wallhaven API.

        Returns:
            Wrapped row with compact link buttons, or None if no links exist.
        """
        links = {
            "Page": wallpaper.get("url"),
            "Short": wallpaper.get("short_url"),
            "Source": wallpaper.get("source"),
        }
        links = {k: v for k, v in links.items() if v}

        if not links:
            return None

        return Row(
            wrap=True,
            spacing=8,
            run_spacing=6,
            controls=[
                FilledTonalButton(
                    height=28,
                    content=Text(label, size=11),
                    icon=Icons.OPEN_IN_NEW,
                    on_click=self._make_launcher(url),
                )
                for label, url in links.items()
            ],
        )

    def _make_launcher(self, url: str) -> Callable:
        """Return a handler that opens the URL in the system browser.

        Args:
            url: URL to open.

        Returns:
            Async click handler for the link control.
        """

        async def _launch(e) -> None:
            await self.page.launch_url(
                url,
                web_popup_window_name=UrlTarget.BLANK,
            )

        return _launch
