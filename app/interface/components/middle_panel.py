"""Middle panel: scrollable wallpaper grid with infinite scroll."""

import asyncio
import time
from typing import Any, Dict, List

from flet import (
    GridView,
    GestureDetector,
    Container,
    Colors,
    ClipBehavior,
    Icon,
    Icons,
    Image,
    BoxFit,
    OnScrollEvent,
    Stack,
    Text,
    Alignment,
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
        self.spacing = 12
        self.run_spacing = 12
        self.child_aspect_ratio = 16 / 9
        self.padding = 4
        self.controls = []
        self.state_page = 1
        self.has_more = True
        self._wallpapers: List[Dict[str, Any]] = []
        self._filters: Dict[str, Any] = {}
        self._generation = 0

        self._load_lock = asyncio.Lock()
        self._load_wanted = False
        self._in_trigger_zone = False
        self._prefetch_lock = asyncio.Lock()
        self._prefetched_page: List[Dict[str, Any]] | None = None
        self._prefetched_page_number: int | None = None

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
        self._load_wanted = False
        self._in_trigger_zone = False
        self._prefetched_page = None
        self._prefetched_page_number = None

        self.page.run_task(self.load_more)

    async def load_more(self, *args) -> None:
        """Fetch and append the next page of wallpapers.

        Pages are loaded under a lock. While a load is in flight further
        calls only set a wish flag, so the in-flight load re-fires once
        instead of spawning duplicate requests. The page after the one
        just rendered is prefetched in the background, so reaching the
        bottom of a page usually hits the cache.
        """
        if not self.has_more:
            return

        self._load_wanted = True
        if self._load_lock.locked():
            return

        async with self._load_lock:
            generation = self._generation
            self._load_wanted = False
            page_start = time.perf_counter()
            try:
                self._lg.debug(f"Loading page {self.state_page}...")

                wallpapers = self._consume_prefetched()
                if wallpapers is None:
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
                self._lg.debug(
                    f"Page {self.state_page - 1} rendered: "
                    f"{len(wallpapers)} wallpapers added "
                    f"({(time.perf_counter() - page_start) * 1000:.0f} ms), "
                    f"total {len(self._wallpapers)}."
                )
            except Exception as e:
                if generation == self._generation:
                    # Transient 502/503 etc — retry, don't kill pagination
                    msg = str(e).lower()
                    is_transient = any(
                        s in msg
                        for s in ("502", "503", "429", "500", "bad gateway")
                    ) or "transient" in msg
                    if is_transient:
                        self._lg.warning(
                            f"Transient load error, retrying: {e}"
                        )
                        self._load_wanted = False
                        self.page.run_task(self._retry_with_delay, 1.0)
                    else:
                        self._lg.critical(f"Internal error: {e}.")
                return

        if self._load_wanted and self.has_more:
            self.page.run_task(self.load_more)
        elif self.has_more:
            self.page.run_task(self._prefetch_next_page)

    async def _retry_with_delay(self, delay: float) -> None:
        """Retry load_more after delay."""
        await asyncio.sleep(delay)
        await self.load_more()

    def _consume_prefetched(self) -> List[Dict[str, Any]] | None:
        """Return the cached next page when it matches the current one.

        Stale prefetches (the grid has already advanced past the cached
        page number) are dropped so they never block a newer prefetch.

        Returns:
            The prefetched wallpaper list, or None to load via network.
        """
        if (
            self._prefetched_page is not None
            and self._prefetched_page_number == self.state_page
        ):
            data = self._prefetched_page
            self._prefetched_page = None
            self._prefetched_page_number = None
            return data
        if self._prefetched_page is not None:
            self._prefetched_page = None
            self._prefetched_page_number = None
        return None

    async def _prefetch_next_page(self) -> None:
        """Fetch the page after the rendered one into the background cache.

        Fire-and-forget: transient failures just leave the cache empty and
        the explicit load retries on its own; an empty page marks the end.
        """
        if not self.has_more or self._prefetch_lock.locked():
            return
        if self._prefetched_page is not None:
            return

        generation = self._generation
        page = self.state_page
        async with self._prefetch_lock:
            if self._prefetched_page is not None:
                return
            self._lg.debug(f"Prefetching page {page} in background...")
            try:
                data = await self.api_client.search_wallpapers(
                    page=page, **self._filters
                )
            except Exception as e:
                msg = str(e).lower()
                is_transient = any(
                    s in msg
                    for s in ("502", "503", "429", "500", "bad gateway")
                ) or "transient" in msg
                self._lg.debug(
                    f"Prefetch of page {page} skipped "
                    f"({'transient' if is_transient else 'error'}): {e}"
                )
                return
            if generation != self._generation:
                return
            if not data:
                self.has_more = False
                return
            self._prefetched_page = data
            self._prefetched_page_number = page
            self._lg.debug(f"Prefetched page {page} ({len(data)} items).")

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

        C3: Card-like tile with rounded corners, shadow and info overlay.

        Args:
            wallpaper: Wallpaper dict from the API.
            index: Index of the wallpaper in the local cache.

        Returns:
            Gesture detector with single and double click handlers.
        """
        # resolution label for overlay (if available)
        res = wallpaper.get("resolution") or wallpaper.get("dimension") or ""
        # Use Stack to overlay resolution chip when hover? Keep simple.
        img = Image(
            src=wallpaper["thumbs"]["small"],
            fit=BoxFit.COVER,
            border_radius=12,
            error_content=Icon(Icons.BROKEN_IMAGE, color=Colors.OUTLINE_VARIANT, size=24),
        )
        return GestureDetector(
            data=index,
            on_tap=self.handle_image_click,
            on_double_tap=self.handle_image_double_click,
            content=Container(
                border_radius=12,
                bgcolor=Colors.SURFACE_CONTAINER_HIGHEST,
                clip_behavior=ClipBehavior.HARD_EDGE,
                shadow=None,
                content=Stack(
                    controls=[
                        img,
                        Container(
                            alignment=Alignment.BOTTOM_RIGHT,
                            padding=4,
                            content=Container(
                                padding=4,
                                border_radius=8,
                                bgcolor=Colors.BLACK54,
                                visible=bool(res),
                                content=Text(
                                    str(res),
                                    size=10,
                                    color=Colors.WHITE,
                                    weight="w500",
                                ),
                            )
                            if res
                            else None,
                        ),
                    ]
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