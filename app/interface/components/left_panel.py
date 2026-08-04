"""Left panel: search, API key and filters for the wallpaper gallery."""

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
            on_submit=lambda e: self._apply(),
        )

        self._api_key_field = TextField(
            label="API key",
            hint_text="Required for NSFW / favorites",
            password=True,
            can_reveal_password=True,
            value=config.data.APIK,
            on_change=self._handle_api_key_change,
        )

        self._general_cb = Checkbox(label="General", value=True)
        self._anime_cb = Checkbox(label="Anime", value=True)
        self._people_cb = Checkbox(label="People", value=True)

        has_key = bool(config.data.APIK)
        self._sfw_cb = Checkbox(label="SFW", value=True)
        self._sketchy_cb = Checkbox(
            label="Sketchy", value=False, disabled=not has_key
        )
        self._nsfw_cb = Checkbox(label="NSFW", value=False, disabled=not has_key)

        self._sorting_dd = Dropdown(
            label="Sorting",
            value="date_added",
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
            options=[
                DropdownOption(key="desc", text="Descending"),
                DropdownOption(key="asc", text="Ascending"),
            ],
        )

        self._atleast_dd = Dropdown(
            label="Resolution (at least)",
            value="Any",
            options=[
                DropdownOption(key=r, text=r)
                for r in RESOLUTIONS
            ],
        )

        self._ratios_dd = Dropdown(
            label="Aspect ratio",
            value="Any",
            options=[
                DropdownOption(key=r, text=r)
                for r in RATIOS
            ],
        )

        self._colors_dd = Dropdown(
            label="Color",
            value="",
            options=[
                DropdownOption(key=hex_value, text=label)
                for label, hex_value in COLORS
            ],
        )

        self._top_range_dd = Dropdown(
            label="Toplist range",
            value="1M",
            options=[
                DropdownOption(key=r, text=r)
                for r in TOP_RANGES
            ],
        )

        self._apply_button = FilledButton(
            content="Apply Search",
            icon=Icons.SEARCH,
            on_click=lambda e: self._apply(),
        )

        return ListView(
            expand=True,
            spacing=10,
            controls=[
                Text("Search", size=14, weight="w700"),
                self._search_field,
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
                self._apply_button,
            ],
        )

    def _handle_api_key_change(self, e) -> None:
        """Enable or disable purity filters depending on the API key.

        Args:
            e: Change event from the API key field.
        """
        has_key = bool((self._api_key_field.value or "").strip())
        self._sketchy_cb.disabled = not has_key
        self._nsfw_cb.disabled = not has_key
        self.update()

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

        if api_key != config.data.APIK:
            config.data.APIK = api_key
            config.save()

        self._lg.debug(f"Applied filters: {api_key!r}.")
        self._middle.apply_filters(api_key, self._collect_filters())