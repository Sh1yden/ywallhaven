"""Collection settings: left panel content in collections mode.

Edits the selected collection in place (name, slideshow, interval,
order, fit, cover mode); every change persists via the store and
notifies through the ``on_changed`` callback so the grid and the
properties panel stay in sync. Folders show info + refresh/unlink.
"""

from typing import Any, Callable, Dict

from flet import (
    Alignment,
    Colors,
    Column,
    Container,
    Dropdown,
    DropdownOption,
    FilledTonalButton,
    Icons,
    Switch,
    Text,
    TextField,
)

_ORDER_OPTIONS = ["sequential", "random"]
_FIT_OPTIONS = ["fill", "fit"]
_COVER_MODES = ["last", "icon", "wallpaper", "heart"]


class CollectionSettingsPanel(Container):
    """Settings form for the selected collection or folder."""

    def __init__(
        self,
        store: Any,
        on_changed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self._store = store
        self._on_changed = on_changed
        self.expand = 1
        self.padding = 14
        self.bgcolor = Colors.SURFACE_CONTAINER
        self.border_radius = 16
        self._collection_id: str | None = None
        self._folder_id: str | None = None
        self.content = self._empty_hint()

    # Loading ------------------------------------------------------

    def load_collection(self, collection: Dict[str, Any]) -> None:
        """Show the settings form of a collection."""
        self._collection_id = collection.get("id", "")
        self._folder_id = None
        settings = collection.get("settings") or {}
        cover = collection.get("cover") or {}
        self.content = Column(
            expand=True,
            spacing=12,
            controls=[
                Text(
                    "Collection settings",
                    size=13,
                    weight="w700",
                    color=Colors.ON_SURFACE,
                ),
                self._name_field(collection.get("name", "")),
                self._slideshow_switch(
                    bool(settings.get("slideshow", False))
                ),
                self._interval_field(settings.get("interval", 300)),
                self._order_dropdown(
                    str(settings.get("order", "sequential"))
                ),
                self._fit_dropdown(str(settings.get("fit", "fill"))),
                self._cover_dropdown(str(cover.get("mode", "last"))),
            ],
        )
        self._safe_update()

    def load_folder(self, folder: Dict[str, Any], count: int) -> None:
        """Show info and actions of a linked photo folder."""
        self._collection_id = None
        self._folder_id = folder.get("id", "")
        settings = folder.get("settings") or {}
        self.content = Column(
            expand=True,
            spacing=12,
            controls=[
                Text(
                    "Folder collection",
                    size=13,
                    weight="w700",
                    color=Colors.ON_SURFACE,
                ),
                Text(
                    folder.get("path", ""),
                    size=12,
                    selectable=True,
                    color=Colors.ON_SURFACE_VARIANT,
                ),
                Text(
                    f"{count} photos",
                    size=12,
                    color=Colors.ON_SURFACE_VARIANT,
                ),
                self._folder_slideshow_switch(
                    bool(settings.get("slideshow", False))
                ),
                self._folder_interval_field(settings.get("interval", 300)),
                FilledTonalButton(
                    content="Refresh",
                    icon=Icons.REFRESH,
                    on_click=self._handle_refresh,
                ),
                FilledTonalButton(
                    content="Unlink folder",
                    icon=Icons.LINK_OFF,
                    on_click=self._handle_unlink,
                ),
                Text(
                    "Files on disk are never touched.",
                    size=11,
                    color=Colors.ON_SURFACE_VARIANT,
                ),
            ],
        )
        self._safe_update()

    def show_empty(self) -> None:
        """Show the idle hint when nothing is selected."""
        self._collection_id = None
        self._folder_id = None
        self.content = self._empty_hint()
        self._safe_update()

    @staticmethod
    def _empty_hint() -> Container:
        """Build the idle placeholder."""
        return Container(
            alignment=Alignment.CENTER,
            content=Text(
                "Select a collection",
                size=12,
                color=Colors.ON_SURFACE_VARIANT,
                text_align="center",
            ),
        )

    def _safe_update(self) -> None:
        """Push control updates, tolerating a detached tree."""
        try:
            self.update()
        except Exception:
            pass

    def _emit_changed(self) -> None:
        """Tell the owner to refresh grid and properties."""
        if self._on_changed is not None:
            self._on_changed()

    # Controls -------------------------------------------------------

    def _name_field(self, value: str) -> TextField:
        """Build the collection name editor."""
        field = TextField(
            label="Name",
            value=value,
            filled=True,
        )

        def _save(e) -> None:
            if self._collection_id and (field.value or "").strip():
                self._store.rename(
                    self._collection_id, field.value.strip()
                )
                self._emit_changed()

        field.on_submit = _save
        field.on_blur = _save
        return field

    def _slideshow_switch(self, value: bool) -> Switch:
        """Build the slideshow toggle."""
        switch = Switch(label="Slideshow", value=value)

        def _save(e) -> None:
            if self._collection_id:
                self._store.update_settings(
                    self._collection_id,
                    slideshow=bool(switch.value),
                )
                self._emit_changed()

        switch.on_change = _save
        return switch

    def _interval_field(self, value: Any) -> TextField:
        """Build the slideshow interval editor (seconds)."""
        field = TextField(
            label="Interval, seconds",
            value=str(value),
            filled=True,
        )

        def _save(e) -> None:
            if not self._collection_id:
                return
            try:
                interval = int((field.value or "").strip())
            except (ValueError, TypeError):
                field.error = "Invalid number"
                self._safe_update()
                return
            if interval < 10:
                field.error = "Minimum 10 seconds"
                self._safe_update()
                return
            field.error = None
            self._store.update_settings(
                self._collection_id, interval=interval
            )
            self._emit_changed()

        field.on_submit = _save
        field.on_blur = _save
        return field

    def _order_dropdown(self, value: str) -> Dropdown:
        """Build the slideshow order selector."""
        dropdown = Dropdown(
            label="Order",
            value=value if value in _ORDER_OPTIONS else "sequential",
            options=[
                DropdownOption(key=o, text=o) for o in _ORDER_OPTIONS
            ],
        )

        def _save(e) -> None:
            if self._collection_id and dropdown.value:
                self._store.update_settings(
                    self._collection_id, order=dropdown.value
                )
                self._emit_changed()

        dropdown.on_select = _save
        return dropdown

    def _fit_dropdown(self, value: str) -> Dropdown:
        """Build the wallpaper fit selector."""
        dropdown = Dropdown(
            label="Fit",
            value=value if value in _FIT_OPTIONS else "fill",
            options=[
                DropdownOption(key=o, text=o) for o in _FIT_OPTIONS
            ],
        )

        def _save(e) -> None:
            if self._collection_id and dropdown.value:
                self._store.update_settings(
                    self._collection_id, fit=dropdown.value
                )
                self._emit_changed()

        dropdown.on_select = _save
        return dropdown

    def _cover_dropdown(self, value: str) -> Dropdown:
        """Build the cover mode selector."""
        dropdown = Dropdown(
            label="Cover",
            value=value if value in _COVER_MODES else "last",
            options=[
                DropdownOption(key=o, text=o) for o in _COVER_MODES
            ],
        )

        def _save(e) -> None:
            if self._collection_id and dropdown.value:
                self._store.set_cover(
                    self._collection_id, {"mode": dropdown.value}
                )
                self._emit_changed()

        dropdown.on_select = _save
        return dropdown

    def _folder_slideshow_switch(self, value: bool) -> Switch:
        """Build the folder slideshow toggle."""
        switch = Switch(label="Slideshow", value=value)

        def _save(e) -> None:
            if self._folder_id:
                self._store.update_folder_settings(
                    self._folder_id,
                    slideshow=bool(switch.value),
                )
                self._emit_changed()

        switch.on_change = _save
        return switch

    def _folder_interval_field(self, value: Any) -> TextField:
        """Build the folder interval editor (seconds)."""
        field = TextField(
            label="Interval, seconds",
            value=str(value),
            filled=True,
        )

        def _save(e) -> None:
            if not self._folder_id:
                return
            try:
                interval = int((field.value or "").strip())
            except (ValueError, TypeError):
                field.error = "Invalid number"
                self._safe_update()
                return
            if interval < 10:
                field.error = "Minimum 10 seconds"
                self._safe_update()
                return
            field.error = None
            self._store.update_folder_settings(
                self._folder_id, interval=interval
            )
            self._emit_changed()

        field.on_submit = _save
        field.on_blur = _save
        return field

    def _handle_refresh(self, e) -> None:
        """Republish the selection so folder content rescans."""
        self._emit_changed()

    def _handle_unlink(self, e) -> None:
        """Unlink the folder via the store (files untouched)."""
        if self._folder_id:
            self._store.remove_folder(self._folder_id)
            self.show_empty()
            self._emit_changed()
