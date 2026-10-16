"""Collections grid: collapsed collections view for the middle area.

Shows one tile per collection (cover + name + counter), one tile per
linked photo folder, and a create tile. All mutations live in
``flet_app`` (it owns the store); this panel only renders and
publishes selection/creation requests over the bus.
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
    Icons,
    Image,
    BoxFit,
    Text,
)

from app.interface import bus


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
    """Grid of collection/folder tiles with a create tile."""

    def __init__(self, store: Any) -> None:
        super().__init__()
        self._store = store
        self.expand = 3
        self.padding = 4
        self.bgcolor = Colors.TRANSPARENT
        self._grid = GridView(
            expand=True,
            runs_count=3,
            spacing=12,
            run_spacing=12,
            child_aspect_ratio=1.0,
            padding=4,
        )
        self.content = self._grid
        self.refresh()

    def refresh(self) -> None:
        """Rebuild tiles from the store (collections + folders)."""
        tiles: List[Any] = []
        for collection in self._store.collections():
            tiles.append(self._collection_tile(collection))
        for folder in self._store.folders():
            tiles.append(self._folder_tile(folder))
        tiles.append(self._create_tile())
        self._grid.controls = tiles
        try:
            self._grid.update()
        except Exception:
            pass

    def _select(
        self, kind: str, item_id: str
    ) -> Callable[[Any], None]:
        """Return a tap handler publishing the selection."""

        def handler(e) -> None:
            bus.publish(
                getattr(self, "page", None),
                bus.TOPIC_COLLECTION_SELECT,
                {"kind": kind, "id": item_id},
            )

        return handler

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
