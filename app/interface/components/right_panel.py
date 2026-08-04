"""Right panel: preview and properties of the selected wallpaper."""

from typing import Any, Callable, Dict, List

from flet import (
    Alignment,
    BoxFit,
    ClipBehavior,
    Colors,
    Column,
    Container,
    FilledButton,
    Icons,
    Image,
    Row,
    Stack,
    Text,
    TextSpan,
    TextStyle,
    TextDecoration,
)
from app.service import WallhavenAPI


class RightPanel(Container):
    """Preview and properties panel for the selected wallpaper."""

    PREVIEW_RADIUS = 12
    GAP = 12

    def __init__(
        self, on_download: Callable[[str, str], None]
    ) -> None:
        super().__init__()
        self._on_download = on_download
        self.expand = 1
        self.padding = 12
        self.bgcolor = Colors.DEEP_PURPLE_500
        self.alignment = Alignment.CENTER
        self.content = self._build_empty_state()
        self._last_wallpaper: Dict[str, Any] | None = None
        self._fullscreen_layer: Container | None = None
        self._fullscreen_image: Image | None = None

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

    # Public API ----------------------------------------------------

    def update_preview(self, wallpaper: Dict[str, Any]) -> None:
        """Show the preview and properties of a wallpaper.

        Args:
            wallpaper: Wallpaper dict from the Wallhaven API.
        """
        self._last_wallpaper = wallpaper
        self.content = Column(
            expand=True,
            spacing=self.GAP,
            controls=[
                self._build_preview(wallpaper),
                self._build_properties(wallpaper),
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
            expand=True,
        )

    def _handle_download_click(self, e) -> None:
        """Ask the app to save the current wallpaper.

        Args:
            e: Click event from the download button.
        """
        if self._last_wallpaper is None or self._on_download is None:
            return

        self._on_download(
            self._last_wallpaper.get("path", ""),
            WallhavenAPI.build_filename(self._last_wallpaper),
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
            bgcolor=Colors.GREY_900,
            on_click=self.open_fullscreen,
            content=Image(
                src=wallpaper.get("path"),
                fit=BoxFit.COVER,
                expand=True,
            ),
        )

    def _build_fullscreen_layer(self) -> Container:
        """Build the fullscreen overlay shown on preview click.

        Returns:
            Fullscreen container with the wallpaper image.
        """
        self._fullscreen_image = Image(
            src="",
            fit=BoxFit.CONTAIN,
            expand=True,
        )

        self._fullscreen_layer = Container(
            visible=False,
            expand=True,
            bgcolor=Colors.BLACK,
            content=Stack(
                expand=True,
                controls=[
                    self._fullscreen_image,
                    Container(
                        expand=True,
                        bgcolor=Colors.TRANSPARENT,
                        on_click=self.close_fullscreen,
                    ),
                ],
            ),
        )

        return self._fullscreen_layer

    def open_fullscreen(self, e) -> None:
        """Show the current wallpaper image in fullscreen.

        Args:
            e: Click event from the preview container.
        """
        if self._last_wallpaper is None or self._fullscreen_layer is None:
            return

        self._fullscreen_image.src = self._last_wallpaper.get("path")
        self._fullscreen_layer.visible = True
        self._fullscreen_layer.update()

    def close_fullscreen(self, e) -> None:
        """Hide the fullscreen overlay.

        Args:
            e: Click event from the fullscreen layer.
        """
        if self._fullscreen_layer is None:
            return

        self._fullscreen_layer.visible = False
        self._fullscreen_layer.update()

    def _build_properties(self, wallpaper: Dict[str, Any]) -> Column:
        """Build the properties column from a wallpaper dict.

        Args:
            wallpaper: Wallpaper dict from the Wallhaven API.

        Returns:
            Column with property rows, colors, tags and links.
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

        return Column(
            spacing=6,
            controls=[c for c in controls if c is not None],
        )

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

    @staticmethod
    def _make_tags_row(tags: Any) -> Row | None:
        """Build a row of tag chips.

        Args:
            tags: List of tag dicts from the API.

        Returns:
            Wrapped row with tag chips, or None if no tags are present.
        """
        if not tags:
            return None

        return Row(
            wrap=True,
            spacing=6,
            run_spacing=6,
            controls=[
                Container(
                    padding=6,
                    border_radius=6,
                    bgcolor=Colors.GREY_800,
                    content=Text(
                        tag.get("name", ""),
                        size=11,
                    ),
                )
                for tag in tags
            ],
        )

    def _make_links_row(self, wallpaper: Dict[str, Any]) -> Row | None:
        """Build clickable links for a wallpaper.

        Args:
            wallpaper: Wallpaper dict from the Wallhaven API.

        Returns:
            Wrapped row with clickable links, or None if no links exist.
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
            spacing=10,
            run_spacing=6,
            controls=[
                Text(
                    size=12,
                    spans=[
                        TextSpan(
                            text=label,
                            style=TextStyle(
                                color=Colors.BLUE_200,
                                decoration=TextDecoration.UNDERLINE,
                            ),
                            on_click=self._make_launcher(url),
                        )
                    ],
                )
                for label, url in links.items()
            ],
        )

    def _make_launcher(self, url: str) -> Callable:
        """Return a handler that opens the URL in a browser.

        Args:
            url: URL to open.

        Returns:
            Click handler for the link control.
        """

        def _launch(e) -> None:
            self.page.launch_url(url)

        return _launch
