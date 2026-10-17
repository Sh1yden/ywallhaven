"""Collections grid: collapsed collections view for the middle area.

Shows one tile per collection (cover + name + counter), one tile per
linked photo folder, and a create tile. Tapping a tile drills down
into its wallpapers (tap preview, double-tap download); the header
back button returns to the list. All mutations live in ``flet_app``
(it owns the store); this panel only renders and publishes
selection/creation requests over the bus.
"""

from typing import Any, Callable, Dict, List

from flet import (
    Alignment,
    ClipBehavior,
    Colors,
    Column,
    Container,
    CrossAxisAlignment,
    GestureDetector,
    GridView,
    Icon,
    IconButton,
    Icons,
    Image,
    BoxFit,
    MainAxisAlignment,
    Row,
    Stack,
    Text,
)

from app.interface import bus

ICON_PRESETS = (
    "FAVORITE",
    "IMAGE",
    "LANDSCAPE",
    "FOLDER",
    "STAR",
    "HOME",
    "WORK",
    "PEOPLE",
    "LOCATION_CITY",
    "ROCKET_LAUNCH",
    "PETS",
    "DIRECTIONS_CAR",
    "SPORTS_SOCCER",
    "MUSIC_NOTE",
    "VIDEOGAME_ASSET",
    "FLIGHT",
    "BEACH_ACCESS",
    "TERRAIN",
    "WB_SUNNY",
    "NIGHTLIGHT",
    "BRUSH",
    "PUBLIC",
    "FOREST",
    "CAKE",
)


def thumb_src(wallpaper: Dict[str, Any]) -> str | None:
    """Return the best thumbnail source of a wallpaper dict."""
    thumbs = wallpaper.get("thumbs") or {}
    return thumbs.get("small") or wallpaper.get("path")


def resolve_cover(collection: Dict[str, Any]) -> tuple[str, Any]:
    """Resolve a collection cover to a renderable descriptor.

    Args:
        collection: Collection dict from the favorites store.

    Returns:
        (kind, value) where kind is "icon" (Flet icon name),
        "image" (thumbnail src) or "heart" (empty placeholder).
    """
    cover = collection.get("cover") or {}
    mode = cover.get("mode", "last")
    walls = collection.get("wallpapers") or []
    if mode == "icon":
        return ("icon", cover.get("icon") or "IMAGE")
    if mode == "wallpaper":
        wanted = cover.get("wallpaper_id", "")
        for wall in walls:
            if str(wall.get("id", "")) == str(wanted):
                src = thumb_src(wall)
                return ("image", src) if src else ("heart", None)
        return ("heart", None)
    if walls:
        src = thumb_src(walls[-1])
        return ("image", src) if src else ("heart", None)
    return ("heart", None)


class CollectionsPanel(Container):
    """Grid of collection/folder tiles with drill-down contents."""

    # Top-left action zone (DIP) for the remove button.
    REMOVE_ZONE_WIDTH = 44.0
    REMOVE_ZONE_HEIGHT = 44.0

    def __init__(self, store: Any) -> None:
        super().__init__()
        self._store = store
        self.expand = 3
        self.padding = 4
        self.bgcolor = Colors.TRANSPARENT
        self._open_kind: str | None = None
        self._open_id: str | None = None
        self._selecting = False
        self._checked: set = set()
        self._grid = GridView(
            expand=True,
            runs_count=3,
            spacing=12,
            run_spacing=12,
            child_aspect_ratio=1.0,
            padding=4,
        )
        # NOTE: the grid lives in the same slot for the panel's whole
        # lifetime; render modes swap only the header content and the
        # grid rows. Moving the control between parents (old code
        # reparented it into a Column on drill-down) made the Flet
        # diff leave ghost tiles in the mounted client: duplicated
        # collections and "New collection" tiles after leaving a
        # collection.
        self._header = Container()
        self.content = Column(
            expand=True,
            spacing=8,
            controls=[self._header, self._grid],
        )
        self.refresh()

    # Navigation -----------------------------------------------------

    def open_collection(self, kind: str, item_id: str) -> None:
        """Drill down into a collection or folder wallpapers."""
        self._open_kind = kind
        self._open_id = item_id
        self._selecting = False
        self._checked = set()
        self.refresh()

    def go_list(self) -> None:
        """Return to the collapsed collections list."""
        self._open_kind = None
        self._open_id = None
        self._selecting = False
        self._checked = set()
        self.refresh()

    def get_selected_wallpapers(self) -> List[Dict[str, Any]]:
        """Return checked wallpapers of the opened entry."""
        _title, walls = self._open_items()
        return [
            walls[pos] for pos in sorted(self._checked) if pos < len(walls)
        ]

    @property
    def is_open(self) -> bool:
        """Return True while showing collection contents."""
        return self._open_kind is not None

    def _open_items(self) -> tuple[str, List[Dict[str, Any]]]:
        """Resolve title and wallpapers of the opened entry."""
        if self._open_kind == "folder":
            folder = next(
                (
                    f
                    for f in self._store.folders()
                    if f.get("id") == self._open_id
                ),
                None,
            )
            if folder is None:
                return "", []
            return (
                folder.get("name", "?"),
                self._store.scan_folder(folder.get("path", "")),
            )
        collection = self._store.get(self._open_id or "")
        if collection is None:
            return "", []
        return (
            collection.get("name", "?"),
            list(collection.get("wallpapers") or []),
        )

    def refresh(self) -> None:
        """Rebuild the grid for the current view."""
        if self.is_open:
            self._render_contents()
        else:
            self._render_list()
        try:
            self.update()
        except Exception:
            pass

    def _render_list(self) -> None:
        """Render collapsed tiles (collections + folders + create)."""
        self._grid.child_aspect_ratio = 1.0
        tiles: List[Any] = []
        for collection in self._store.collections():
            tiles.append(self._collection_tile(collection))
        for folder in self._store.folders():
            tiles.append(self._folder_tile(folder))
        tiles.append(self._create_tile())
        self._grid.controls = tiles
        # Empty Container renders zero-height: no list header.
        self._header.content = None

    def _render_contents(self) -> None:
        """Render opened wallpapers with a back header."""
        title, walls = self._open_items()
        if not title and not walls:
            self.go_list()
            return
        self._grid.child_aspect_ratio = 16 / 9
        noun = "wallpaper" if len(walls) == 1 else "wallpapers"
        tiles: List[Any] = []
        for position, wallpaper in enumerate(walls):
            tiles.append(self._wallpaper_tile(wallpaper, position))
        self._grid.controls = tiles
        if self._selecting:
            header: Any = Row(
                spacing=4,
                vertical_alignment="center",
                controls=[
                    IconButton(
                        icon=Icons.CLOSE,
                        icon_size=22,
                        tooltip="Exit selection",
                        on_click=lambda e: self.exit_selection(),
                    ),
                    Text(
                        f"{len(self._checked)} selected",
                        size=13,
                        weight="w700",
                        color=Colors.ON_SURFACE,
                        expand=True,
                    ),
                    IconButton(
                        icon=Icons.DELETE,
                        tooltip="Delete selected",
                        on_click=lambda e: self._publish_selected(
                            bus.TOPIC_COLLECTION_DELETE_SELECTED
                        ),
                    ),
                    IconButton(
                        icon=Icons.DOWNLOAD,
                        tooltip="Download selected",
                        on_click=lambda e: self._publish_selected(
                            bus.TOPIC_COLLECTION_DOWNLOAD_SELECTED
                        ),
                    ),
                    IconButton(
                        icon=Icons.DRIVE_FILE_MOVE,
                        tooltip="Add to collection",
                        on_click=lambda e: self._publish_selected(
                            bus.TOPIC_COLLECTION_MOVE_SELECTED
                        ),
                    ),
                    IconButton(
                        icon=Icons.SLIDESHOW,
                        tooltip="Slideshow from selection",
                        on_click=lambda e: self._publish_selected(
                            bus.TOPIC_SLIDESHOW_SELECTION
                        ),
                    ),
                ],
            )
        else:
            header = Row(
                spacing=8,
                vertical_alignment="center",
                controls=[
                    IconButton(
                        icon=Icons.ARROW_BACK,
                        icon_size=22,
                        tooltip="Back to collections",
                        on_click=lambda e: self.go_list(),
                    ),
                    Text(
                        title,
                        size=15,
                        weight="w700",
                        color=Colors.ON_SURFACE,
                        expand=True,
                    ),
                    Text(
                        f"{len(walls)} {noun}",
                        size=11,
                        color=Colors.ON_SURFACE_VARIANT,
                    ),
                ],
            )
        self._header.content = header

    def _publish_selected(self, topic: str) -> None:
        """Publish checked wallpaper ids on a bus topic."""
        _title, walls = self._open_items()
        ids = [
            str(walls[pos].get("id", ""))
            for pos in sorted(self._checked)
            if pos < len(walls)
        ]
        bus.publish(
            getattr(self, "page", None),
            topic,
            {
                "kind": self._open_kind or "collection",
                "id": self._open_id or "",
                "wallpaper_ids": ids,
            },
        )

    def exit_selection(self) -> None:
        """Leave selection mode and redraw."""
        self._selecting = False
        self._checked = set()
        self.refresh()

    def _select(
        self, kind: str, item_id: str
    ) -> Callable[[Any], None]:
        """Return a tap handler opening and selecting an entry."""

        def handler(e) -> None:
            self.open_collection(kind, item_id)
            bus.publish(
                getattr(self, "page", None),
                bus.TOPIC_COLLECTION_SELECT,
                {"kind": kind, "id": item_id},
            )

        return handler

    def _wallpaper_tile(
        self, wallpaper: Dict[str, Any], position: int
    ) -> GestureDetector:
        """Build a contents tile (preview, remove, multiselect).

        A single detector owns every gesture: taps dispatch by zone
        (top-left remove in normal mode), long-press enters selection
        mode, taps toggle checks there.
        """

        def _tap(e) -> None:
            if self._selecting:
                self._toggle_check(position)
                return
            point = self._tap_point(e)
            if point is not None:
                x, y = point
                if (
                    x < self.REMOVE_ZONE_WIDTH
                    and y < self.REMOVE_ZONE_HEIGHT
                    and self._open_kind == "collection"
                ):
                    bus.publish(
                        getattr(self, "page", None),
                        bus.TOPIC_COLLECTION_REMOVE_ONE,
                        {
                            "kind": "collection",
                            "id": self._open_id or "",
                            "wallpaper_id": str(
                                wallpaper.get("id", "")
                            ),
                        },
                    )
                    return
            bus.publish(
                getattr(self, "page", None),
                bus.TOPIC_PREVIEW,
                {"wallpaper": wallpaper, "index": None},
            )

        def _long_press(e) -> None:
            self._selecting = True
            self._checked = {position}
            self.refresh()

        def _download(e) -> None:
            bus.publish(
                getattr(self, "page", None),
                bus.TOPIC_DOWNLOAD_REQUEST,
                {"wallpaper": wallpaper},
            )

        overlays: List[Any] = []
        if self._selecting:
            checked = position in self._checked
            overlays.append(
                Container(
                    alignment=Alignment.TOP_RIGHT,
                    padding=6,
                    content=Icon(
                        Icons.CHECK_BOX
                        if checked
                        else Icons.CHECK_BOX_OUTLINE_BLANK,
                        size=24,
                        color=Colors.PRIMARY
                        if checked
                        else Colors.WHITE,
                    ),
                )
            )
        elif self._open_kind == "collection":
            overlays.append(
                Container(
                    alignment=Alignment.TOP_LEFT,
                    padding=4,
                    content=Container(
                        padding=2,
                        border_radius=8,
                        bgcolor=Colors.BLACK54,
                        content=Icon(
                            Icons.CLOSE,
                            size=16,
                            color=Colors.WHITE,
                        ),
                    ),
                )
            )
        src = thumb_src(wallpaper)
        return GestureDetector(
            data=position,
            on_tap=_tap,
            on_long_press=_long_press,
            on_double_tap=_download,
            content=Container(
                border_radius=12,
                bgcolor=Colors.SURFACE_CONTAINER_HIGHEST,
                clip_behavior=ClipBehavior.HARD_EDGE,
                content=Stack(
                    controls=[
                        (
                            Image(
                                src=src,
                                fit=BoxFit.COVER,
                                expand=True,
                                border_radius=12,
                                error_content=Icon(
                                    Icons.BROKEN_IMAGE,
                                    color=Colors.OUTLINE_VARIANT,
                                    size=24,
                                ),
                            )
                            if src
                            else Container(
                                expand=True,
                                alignment=Alignment.CENTER,
                                content=Icon(
                                    Icons.IMAGE,
                                    size=40,
                                    color=Colors.PRIMARY,
                                ),
                            )
                        ),
                        *overlays,
                    ]
                ),
            ),
        )

    def _toggle_check(self, position: int) -> None:
        """Toggle one checkbox and redraw the header count."""
        if position in self._checked:
            self._checked.discard(position)
        else:
            self._checked.add(position)
        self.refresh()

    @staticmethod
    def _tap_point(e: Any) -> tuple[float, float] | None:
        """Extract tap coordinates relative to the tile."""
        point = getattr(e, "local_position", None)
        if point is None:
            return None
        try:
            return (float(point.x), float(point.y))
        except (TypeError, ValueError, AttributeError):
            return None

    def _cover_content(
        self, kind: str, value: Any, label: str
    ) -> Any:
        """Build the cover widget (image, icon or heart)."""
        if kind == "image":
            return Image(
                src=value,
                fit=BoxFit.COVER,
                expand=True,
                border_radius=12,
                error_content=Icon(
                    Icons.BROKEN_IMAGE,
                    color=Colors.OUTLINE_VARIANT,
                    size=24,
                ),
            )
        icon_name = "FAVORITE" if kind == "heart" else value
        icon = getattr(Icons, str(icon_name), Icons.IMAGE)
        return Container(
            expand=True,
            alignment=Alignment.CENTER,
            content=Icon(icon, size=40, color=Colors.PRIMARY),
        )

    def _tile_shell(
        self,
        kind: str,
        value: Any,
        title: str,
        subtitle: str,
        on_tap: Callable,
    ) -> GestureDetector:
        """Wrap cover + labels into a clickable card tile."""
        return GestureDetector(
            on_tap=on_tap,
            content=Container(
                border_radius=12,
                bgcolor=Colors.SURFACE_CONTAINER_HIGHEST,
                clip_behavior=ClipBehavior.HARD_EDGE,
                content=Column(
                    spacing=0,
                    controls=[
                        Container(
                            expand=True,
                            clip_behavior=ClipBehavior.HARD_EDGE,
                            content=self._cover_content(
                                kind, value, title
                            ),
                        ),
                        Container(
                            padding=8,
                            content=Column(
                                spacing=0,
                                tight=True,
                                controls=[
                                    Text(
                                        title,
                                        size=13,
                                        weight="w700",
                                        color=Colors.ON_SURFACE,
                                    ),
                                    Text(
                                        subtitle,
                                        size=11,
                                        color=(
                                            Colors.ON_SURFACE_VARIANT
                                        ),
                                    ),
                                ],
                            ),
                        ),
                    ],
                ),
            ),
        )

    def _collection_tile(self, collection: Dict[str, Any]) -> Any:
        """Build a tile for one collection."""
        kind, value = resolve_cover(collection)
        count = len(collection.get("wallpapers") or [])
        noun = "wallpaper" if count == 1 else "wallpapers"
        return self._tile_shell(
            kind,
            value,
            collection.get("name", "?"),
            f"{count} {noun}",
            self._select("collection", collection.get("id", "")),
        )

    def _folder_tile(self, folder: Dict[str, Any]) -> Any:
        """Build a tile for one linked photo folder."""
        try:
            count = len(self._store.scan_folder(folder.get("path", "")))
        except Exception:
            count = 0
        noun = "photo" if count == 1 else "photos"
        return self._tile_shell(
            "icon",
            "FOLDER",
            folder.get("name", "?"),
            f"{count} {noun}",
            self._select("folder", folder.get("id", "")),
        )

    def _create_tile(self) -> Any:
        """Build the create-collection tile."""

        def _request_create(e) -> None:
            bus.publish(
                getattr(self, "page", None),
                bus.TOPIC_COLLECTION_CREATE,
                {},
            )

        return GestureDetector(
            on_tap=_request_create,
            content=Container(
                border_radius=12,
                bgcolor=Colors.SURFACE_CONTAINER_HIGHEST,
                alignment=Alignment.CENTER,
                content=Column(
                    tight=True,
                    horizontal_alignment=CrossAxisAlignment.CENTER,
                    controls=[
                        Icon(
                            Icons.ADD,
                            size=40,
                            color=Colors.PRIMARY,
                        ),
                        Text(
                            "New collection",
                            size=12,
                            color=Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                ),
            ),
        )
