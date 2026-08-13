"""Middle panel: scrollable wallpaper grid with infinite scroll."""

import asyncio
from typing import Any, Dict, List

from flet import (
    GridView,
    GestureDetector,
    Container,
    Colors,
    ClipBehavior,
    Image,
    BoxFit,
    OnScrollEvent,
)
from app.core import LoggerMixin
from app.core.resources import register
from app.interface.components.right_panel import RightPanel
from app.service import WallhavenAPI


class MiddlePanel(GridView, LoggerMixin):
    """Scrollable grid of wallpaper thumbnails with infinite scroll.

    Caches every loaded wallpaper dict so the right panel can show
    the full properties of a clicked item without an extra API call.
    A single click opens the preview, a double click downloads it.
    """

    SCROLL_THRESHOLD = 300

    def __init__(
        self,
        right_panel: RightPanel,
    ) -> None:
        super().__init__()
        self.right_panel = right_panel
        self.api_client = WallhavenAPI()
        register(self.api_client.close)
        self.expand = 3
        self.runs_count = 4
        self.controls = []
        self.state_page = 1
        self.has_more = True
        self._wallpapers: List[Dict[str, Any]] = []
        self._filters: Dict[str, Any] = {}
        self._generation = 0

        self._load_lock = asyncio.Lock()
        self._in_trigger_zone = False

        self.on_scroll = self.handle_scroll

    def did_mount(self) -> None:
        super().did_mount()
        self.page.run_task(self.load_more)

    def will_unmount(self):
        super().will_unmount()
        self.page.run_task(self.api_client.close)

    def apply_filters(
        self, api_key: str, filters: Dict[str, Any]
    ) -> None:
        """Apply new filters, reset the grid and reload it.

        Args:
            api_key: Wallhaven API key or an empty string.
            filters: Search params passed to the API client.
        """
        self.api_client.apik = api_key
        self._filters = dict(filters)

        self._generation += 1
        self.state_page = 1
        self.has_more = True
        self._wallpapers.clear()
        self.controls.clear()
        self._in_trigger_zone = False

        self.page.run_task(self.load_more)

    async def load_more(self, *args) -> None:
        """Fetch and append the next page of wallpapers."""
        if not self.has_more:
            return

        if self._load_lock.locked():
            self.page.run_task(self._retry_load)
            return

        async with self._load_lock:
            generation = self._generation
            try:
                self._lg.debug(f"Loading page {self.state_page}...")

                wallpapers = await self.api_client.search_wallpapers(
                    page=self.state_page, **self._filters
                )

                if generation != self._generation:
                    return

                if not wallpapers:
                    self._lg.warning("No more wallpapers found.")
                    self.has_more = False
                    return

                start = len(self._wallpapers)
                self._wallpapers.extend(wallpapers)

                self.controls.extend(
                    self._build_title(wallpaper, start + i)
                    for i, wallpaper in enumerate(wallpapers)
                )
                self.state_page += 1
                self.update()
            except Exception as e:
                if generation == self._generation:
                    self._lg.critical(f"Internal error: {e}.")

    async def _retry_load(self) -> None:
        """Wait a bit and retry loading after a stale request."""
        await asyncio.sleep(0.1)
        await self.load_more()

    async def select_relative(
        self, delta: int, index: int | None
    ) -> tuple[int, Dict[str, Any]] | None:
        """Return an adjacent cached wallpaper, loading more if needed.

        Args:
            delta: Offset from the current wallpaper index.
            index: Current wallpaper index in the cache.

        Returns:
            The target index and its wallpaper dict, or None if the
            gallery only holds a single item.
        """
        if not self._wallpapers:
            return None

        current = index if index is not None else 0
        target = current + delta
        if target < 0:
            target = 0

        if target >= len(self._wallpapers) and self.has_more:
            await self.load_more()

        if target >= len(self._wallpapers):
            target = len(self._wallpapers) - 1

        if target < 0 or target >= len(self._wallpapers):
            return None

        return target, self._wallpapers[target]

    def _build_title(
        self, wallpaper: Dict[str, Any], index: int
    ) -> GestureDetector:
        """Build a thumbnail tile for a wallpaper.

        Args:
            wallpaper: Wallpaper dict from the API.
            index: Index of the wallpaper in the local cache.

        Returns:
            Gesture detector with single and double click handlers.
        """
        return GestureDetector(
            data=index,
            on_tap=self.handle_image_click,
            on_double_tap=self.handle_image_double_click,
            content=Container(
                border_radius=8,
                bgcolor=Colors.GREY_500,
                clip_behavior=ClipBehavior.HARD_EDGE,
                content=Image(
                    src=wallpaper["thumbs"]["small"],
                    fit=BoxFit.COVER,
                ),
            ),
        )

    def handle_scroll(self, e: OnScrollEvent) -> None:
        """Load the next page when scrolled near the bottom.

        Args:
            e: Scroll event with the current scroll position.
        """
        if not self.has_more:
            return

        if e.max_scroll_extent <= 0:
            return

        threshold = e.max_scroll_extent - self.SCROLL_THRESHOLD
        near_bottom = e.pixels >= threshold

        if near_bottom and not self._in_trigger_zone:
            self._in_trigger_zone = True
            self.page.run_task(self.load_more)
        elif not near_bottom:
            self._in_trigger_zone = False

    def handle_image_click(self, e) -> None:
        """Show the clicked wallpaper preview in the right panel.

        Args:
            e: Tap event; the control data holds the cache index.
        """
        index = e.control.data
        wallpaper = self._wallpapers[index]
        self._lg.debug(f"Wallpaper index is - {index}.")
        self.right_panel.update_preview(wallpaper, index)

    def handle_image_double_click(self, e) -> None:
        """Show the resolution chooser for the double-clicked wallpaper.

        Args:
            e: Double tap event; the control data holds the cache index.
        """
        index = e.control.data
        wallpaper = self._wallpapers[index]
        self._lg.debug(f"Download requested for index - {index}.")
        self.right_panel.request_download(wallpaper)