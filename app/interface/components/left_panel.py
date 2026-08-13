"""Left panel: search, API key and filters for the wallpaper gallery."""

import asyncio
import json
from typing import Any, Dict

from flet import (
    Checkbox,
    Colors,
    Container,
    Dropdown,
    DropdownOption,
    FilledButton,
    Icons,
    ListView,
    Row,
    Text,
    TextField,
)
from app.core import LoggerMixin, config
from app.interface.components.middle_panel import MiddlePanel

RESOLUTIONS = [
    "Any",
    "1280x720",
    "1280x800",
    "1600x900",
    "1920x1080",
    "1920x1200",
    "2560x1440",
    "2560x1600",
    "3440x1440",
    "3840x1600",
    "3840x2160",
]

RATIOS = [
    "Any",
    "16x9",
    "16x10",
    "21x9",
    "32x9",
    "48x9",
    "4x3",
    "5x4",
    "3x2",
    "9x16",
    "10x16",
    "9x18",
    "1x1",
]

COLORS = [
    ("Any", ""),
    ("Red", "660000"),
    ("Blue", "0066cc"),
    ("Green", "77cc33"),
    ("Purple", "663399"),
    ("Pink", "ea4c88"),
    ("Yellow", "ffff00"),
    ("Orange", "ff9900"),
    ("Black", "000000"),
    ("Grey", "999999"),
    ("White", "ffffff"),
]

TOP_RANGES = [
    "1M",
    "1d",
    "3d",
    "1w",
    "3M",
    "6M",
    "1y",
]


class LeftPanel(Container, LoggerMixin):
    """Search, API key and filters above the wallpaper gallery."""

    def __init__(self, middle_panel: MiddlePanel) -> None:
        super().__init__()
        self._middle = middle_panel
        self.expand = 1
        self.padding = 10
        self.bgcolor = Colors.DEEP_PURPLE_500
        self.content = self._build_panel()

    def _build_panel(self) -> ListView:
        """Build the search, API key and filters column.

        Returns:
            Scrollable list of the left panel controls.
        """
        self._search_field = TextField(
            label="Search",
            hint_text="Keywords, tags, @user...",
            icon=Icons.SEARCH,
            expand=True,
            on_change=self._handle_search_input,
            on_submit=lambda e: self._apply(),
        )

        self._apply_button = FilledButton(
            content="Apply",
            icon=Icons.SEARCH,
            on_click=lambda e: self._apply(),
        )

        self._search_apply_seq = 0

        self._api_key_field = TextField(
            label="API key",
            hint_text="Required for NSFW / favorites",
            password=True,
            can_reveal_password=True,
            value=config.data.APIK,
            on_change=self._handle_api_key_change,
        )

        self._general_cb = Checkbox(
            label="General", value=True, on_change=self._handle_category_change
        )
        self._anime_cb = Checkbox(
            label="Anime", value=True, on_change=self._handle_category_change
        )
        self._people_cb = Checkbox(
            label="People", value=True, on_change=self._handle_category_change
        )

        has_key = bool(config.data.APIK)
        self._sfw_cb = Checkbox(
            label="SFW", value=True, on_change=self._handle_purity_change
        )
        self._sketchy_cb = Checkbox(
            label="Sketchy",
            value=False,
            disabled=not has_key,
            on_change=self._handle_purity_change,
        )
        self._nsfw_cb = Checkbox(
            label="NSFW",
            value=False,
            disabled=not has_key,
            on_change=self._handle_purity_change,
        )

        self._sorting_dd = Dropdown(
            label="Sorting",
            value="date_added",
            on_select=self._handle_sorting_change,
            options=[
                DropdownOption(key="date_added", text="Newest"),
                DropdownOption(key="relevance", text="Relevance"),
                DropdownOption(key="views", text="Views"),
                DropdownOption(key="favorites", text="Favorites"),
                DropdownOption(key="random", text="Random"),
                DropdownOption(key="toplist", text="Toplist"),
            ],
        )

        self._order_dd = Dropdown(
            label="Order",
            value="desc",
            on_select=self._handle_order_change,
            options=[
                DropdownOption(key="desc", text="Descending"),
                DropdownOption(key="asc", text="Ascending"),
            ],
        )

        self._atleast_dd = Dropdown(
            label="Resolution (at least)",
            value="Any",
            on_select=self._handle_atleast_change,
            options=[
                DropdownOption(key=r, text=r)
                for r in RESOLUTIONS
            ],
        )

        self._ratios_dd = Dropdown(
            label="Aspect ratio",
            value="Any",
            on_select=self._handle_ratios_change,
            options=[
                DropdownOption(key=r, text=r)
                for r in RATIOS
            ],
        )

        self._colors_dd = Dropdown(
            label="Color",
            value="",
            on_select=self._handle_color_change,
            options=[
                DropdownOption(key=hex_value, text=label)
                for label, hex_value in COLORS
            ],
        )

        self._top_range_dd = Dropdown(
            label="Toplist range",
            value="1M",
            visible=False,
            on_select=self._handle_top_range_change,
            options=[
                DropdownOption(key=r, text=r)
                for r in TOP_RANGES
            ],
        )

        return ListView(
            expand=True,
            spacing=10,
            controls=[
                Text("Search", size=14, weight="w700"),
                Row(
                    spacing=8,
                    controls=[self._search_field, self._apply_button],
                ),
                self._api_key_field,
                Text("Categories", size=14, weight="w700"),
                self._general_cb,
                self._anime_cb,
                self._people_cb,
                Text("Purity", size=14, weight="w700"),
                self._sfw_cb,
                self._sketchy_cb,
                self._nsfw_cb,
                Text("Options", size=14, weight="w700"),
                self._sorting_dd,
                self._order_dd,
                self._atleast_dd,
                self._ratios_dd,
                self._colors_dd,
                self._top_range_dd,
            ],
        )

    def _handle_category_change(self, e) -> None:
        """Reload the gallery when a category checkbox changes.

        Args:
            e: Change event from a category checkbox.
        """
        self._apply()

    def _handle_purity_change(self, e) -> None:
        """Reload the gallery when a purity checkbox changes.

        Args:
            e: Change event from a purity checkbox.
        """
        self._apply()

    def _handle_api_key_change(self, e) -> None:
        """Enable or disable purity filters depending on the API key.

        Args:
            e: Change event from the API key field.
        """
        has_key = bool((self._api_key_field.value or "").strip())
        self._sketchy_cb.disabled = not has_key
        self._nsfw_cb.disabled = not has_key
        self.update()

    def _handle_sorting_change(self, e) -> None:
        """Show the Toplist range only when toplist sorting is selected.

        Args:
            e: Change event from the sorting dropdown.
        """
        value = self._extract_option_value(e)
        if value is not None:
            self._sorting_dd.value = value
        self._top_range_dd.visible = self._sorting_dd.value == "toplist"
        self.update()
        self._apply()

    def _handle_order_change(self, e) -> None:
        """Sync and apply the order dropdown value after a selection.

        Args:
            e: Change event from the order dropdown.
        """
        self._sync_option_value(self._order_dd, e)
        self._apply()

    def _handle_atleast_change(self, e) -> None:
        """Sync and apply the resolution dropdown value after a selection.

        Args:
            e: Change event from the resolution dropdown.
        """
        self._sync_option_value(self._atleast_dd, e)
        self._apply()

    def _handle_ratios_change(self, e) -> None:
        """Sync and apply the aspect ratio dropdown value after a selection.

        Args:
            e: Change event from the aspect ratio dropdown.
        """
        self._sync_option_value(self._ratios_dd, e)
        self._apply()

    def _handle_color_change(self, e) -> None:
        """Sync and apply the color dropdown value after a selection.

        Args:
            e: Change event from the color dropdown.
        """
        self._sync_option_value(self._colors_dd, e)
        self._apply()

    def _handle_top_range_change(self, e) -> None:
        """Sync and apply the toplist range dropdown value after a selection.

        Args:
            e: Change event from the toplist range dropdown.
        """
        self._sync_option_value(self._top_range_dd, e)
        self._apply()

    @staticmethod
    def _extract_option_value(e) -> str | None:
        """Extract the selected option value from a dropdown select event.

        Args:
            e: Select event from a dropdown.

        Returns:
            The selected option key, or None if none is present.
        """
        value: Any = e.control.value if e.control is not None else None
        if not value:
            value = e.data
        if isinstance(value, dict):
            value = value.get("value") or value.get("key") or ""
        if isinstance(value, str) and value.startswith('"'):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass
        if value is None:
            return None
        return str(value).strip("\"'")

    def _sync_option_value(self, dd: Dropdown, e) -> None:
        """Persist the selected value back on the dropdown control.

        Args:
            dd: Dropdown that fired the event.
            e: Select event from the dropdown.
        """
        value = self._extract_option_value(e)
        if value is None:
            return
        dd.value = value
        self.update()

    def _handle_search_input(self, e) -> None:
        """Clear the validation message and schedule a debounced search.

        Args:
            e: Change event from the search field.
        """
        if self._search_field.error:
            self._search_field.error = None
            self.update()

        self._search_apply_seq += 1
        self.page.run_task(self._apply_search_debounced, self._search_apply_seq)

    async def _apply_search_debounced(self, seq: int) -> None:
        """Apply the search query after typing pauses for a while.

        Args:
            seq: Sequence number of the scheduled apply.
        """
        await asyncio.sleep(0.5)
        if seq != self._search_apply_seq:
            return
        self._apply()

    def _collect_filters(self) -> Dict[str, Any]:
        """Collect the currently selected search filters.

        Returns:
            Dict with search params for the API client.
        """
        api_key = (self._api_key_field.value or "").strip()

        categories = "".join(
            str(int(b))
            for b in (
                self._general_cb.value,
                self._anime_cb.value,
                self._people_cb.value,
            )
        )
        categories = "" if categories == "000" else categories

        if not api_key:
            purity = "100"
        else:
            purity = "".join(
                str(int(b))
                for b in (
                    self._sfw_cb.value,
                    self._sketchy_cb.value,
                    self._nsfw_cb.value,
                )
            )
            purity = "" if purity == "000" else purity

        filters: Dict[str, Any] = {}
        query = (self._search_field.value or "").strip()
        if query:
            filters["query"] = query
        if categories:
            filters["categories"] = categories
        if purity:
            filters["purity"] = purity
        filters["sorting"] = self._sorting_dd.value or "date_added"
        filters["order"] = self._order_dd.value or "desc"
        if self._atleast_dd.value and self._atleast_dd.value != "Any":
            filters["atleast"] = self._atleast_dd.value
        if self._ratios_dd.value and self._ratios_dd.value != "Any":
            filters["ratios"] = self._ratios_dd.value
        if self._colors_dd.value:
            filters["colors"] = self._colors_dd.value
        if self._sorting_dd.value == "toplist":
            filters["topRange"] = self._top_range_dd.value or "1M"

        return filters

    def _apply(self) -> None:
        """Save the API key and reload the gallery with new filters."""
        api_key = (self._api_key_field.value or "").strip()
        query = (self._search_field.value or "").strip()

        if self._sorting_dd.value == "relevance" and not query:
            self._search_field.error = (
                "Relevance sorting requires a search query"
            )
            self._search_field.update()
            return

        if api_key != config.data.APIK:
            config.data.APIK = api_key
            config.save()

        self._lg.debug(f"Applied filters: {api_key!r}.")
        self._middle.apply_filters(api_key, self._collect_filters())

    def search_tag(self, name: str) -> None:
        """Fill the search field with a tag and apply it immediately.

        Args:
            name: Tag name to search for.
        """
        self._search_field.value = name
        self._search_field.update()
        self._apply()

    def set_api_key(self, api_key: str) -> None:
        """Apply an API key edited in the settings panel.

        Args:
            api_key: New Wallhaven API key or an empty string.
        """
        self._api_key_field.value = api_key
        self._apply()