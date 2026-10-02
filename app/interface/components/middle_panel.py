"""Middle panel: scrollable wallpaper grid with infinite scroll."""

import asyncio
import time
from typing import Any, Dict, List

from flet import (
    GridView,
    GestureDetector,
    Container,
    Column,
    FilledButton,
    SnackBar,
    SnackBarBehavior,
    MainAxisAlignment,
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
from app.interface import bus
from app.service import WallhavenAPI


class MiddlePanel(GridView, LoggerMixin):
    """Scrollable grid of wallpaper thumbnails with infinite scroll.

    Caches every loaded wallpaper dict so the right panel can show
    the full properties of a clicked item without an extra API call.
    A single click opens the preview, a double click downloads it.
    """

    SCROLL_THRESHOLD = 300
    MAX_TRANSIENT_RETRIES = 3
    RETRY_BASE_DELAY = 1.0
    OUTAGE_POLL_DELAY = 60.0
    TILE_WINDOW = 120

    def __init__(self) -> None:
        super().__init__()
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
        self._transient_failures = 0

        self._load_lock = asyncio.Lock()
        self._load_wanted = False
        self._in_trigger_zone = False
        self._prefetch_lock = asyncio.Lock()
        self._prefetched_page: List[Dict[str, Any]] | None = None
        self._prefetched_page_number: int | None = None

        self._outage_kind: str | None = None
        self._outage_notified = False
        self._poll_scheduled = False
        self._outage_tile: Container | None = None

        self.on_scroll = self.handle_scroll

    def did_mount(self) -> None:
        super().did_mount()
        self._subscribe_bus()
        self.page.run_task(self.load_more)

    def will_unmount(self):
        self._unsubscribe_bus()
        super().will_unmount()
        self.page.run_task(self.api_client.close)

    def _subscribe_bus(self) -> None:
        """Listen for filter changes coming from the left panel."""
        bus.subscribe(
            getattr(self, "page", None),
            bus.TOPIC_FILTERS,
            self._on_filters_message,
        )

    def _unsubscribe_bus(self) -> None:
        """Stop listening for filter changes."""
        bus.unsubscribe(
            getattr(self, "page", None), bus.TOPIC_FILTERS
        )

    def _on_filters_message(self, topic: str, message: Any) -> None:
        """Reload the gallery with filters received over the bus.

        Args:
            topic: Bus topic (always TOPIC_FILTERS here).
            message: {"api_key": str, "filters": dict} payload.
        """
        payload = message or {}
        self.apply_filters(
            payload.get("api_key", ""), payload.get("filters", {})
        )

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
        self._transient_failures = 0
        self._outage_kind = None
        self._outage_notified = False
        self._poll_scheduled = False
        self._outage_tile = None
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

                # Success (fresh or prefetched): the transient-failure
                # streak ends here. An empty list now means a genuine
                # end-of-feed — API errors raise instead of returning [],
                # so they never reach this branch.
                self._transient_failures = 0
                if self._outage_tile is not None or self._outage_notified:
                    # Silent recovery: the filling grid is the signal.
                    self._hide_outage()

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
                # Window the grid (~5 pages of 24): drop the oldest
                # tiles so RAM and the Flutter image cache stop growing
                # past ~500MB on long scrolls. Stored preview indices
                # may go stale after eviction; click handlers and
                # select_relative clamp them back into range.
                while len(self._wallpapers) > self.TILE_WINDOW:
                    self._wallpapers.pop(0)
                    self.controls.pop(0)
                for pos, tile in enumerate(self.controls):
                    if isinstance(tile, GestureDetector):
                        tile.data = pos
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
                    kind, status = WallhavenAPI.classify_error(e)
                    if self._is_transient_error(
                        e
                    ) and self._transient_failures < self.MAX_TRANSIENT_RETRIES:
                        self._transient_failures += 1
                        delay = self.RETRY_BASE_DELAY * (
                            2 ** (self._transient_failures - 1)
                        )
                        self._lg.warning(
                            f"Transient load error "
                            f"({self._transient_failures}/"
                            f"{self.MAX_TRANSIENT_RETRIES}), retrying in "
                            f"{delay:.0f}s: {e}"
                        )
                        self._load_wanted = False
                        self._show_outage(kind, status)
                        self.page.run_task(self._retry_with_delay, delay)
                    elif self._is_transient_error(e):
                        self._lg.error(
                            "Transient load error, retry limit reached "
                            f"— pagination kept alive: {e}."
                        )
                        self._show_outage(kind, status)
                        self._schedule_poll()
                    elif kind == "site_error":
                        self._lg.error(
                            f"Wallhaven error {status}, no retry: {e}."
                        )
                        self._show_outage(kind, status)
                    else:
                        self._lg.critical(f"Internal error: {e}.")
                        self._show_outage(kind, status)
                return

        if self._load_wanted and self.has_more:
            self.page.run_task(self.load_more)
        elif self.has_more:
            self.page.run_task(self._prefetch_next_page)

    async def _retry_with_delay(self, delay: float) -> None:
        """Retry load_more after delay."""
        await asyncio.sleep(delay)
        await self.load_more()

    @staticmethod
    def _outage_text(kind: str, status: int | None) -> str:
        """User-facing outage message stating whose fault it is.

        Args:
            kind: One of "site_down", "site_error", "app_error" from
                WallhavenAPI.classify_error.
            status: HTTP status when Wallhaven answered, else None.

        Returns:
            Message naming the faulty side.
        """
        if kind == "site_down":
            return (
                f"Wallhaven is down (HTTP {status}). "
                "Retrying automatically…"
            )
        if kind == "site_error":
            return (
                f"Wallhaven returned an error (HTTP {status}). "
                "Try different filters or Retry."
            )
        return (
            "App error: could not reach Wallhaven. "
            "Check the logs and Retry."
        )

    def _show_outage(self, kind: str, status: int | None) -> None:
        """Render the outage state and notify once per episode.

        A placeholder tile with a Retry button is added only when the
        grid is empty; otherwise a single SnackBar is enough so loaded
        tiles are never wiped. The SnackBar fires once until the next
        success or filter change.

        Args:
            kind: Fault origin from WallhavenAPI.classify_error.
            status: HTTP status when Wallhaven answered, else None.
        """
        self._outage_kind = kind
        page = getattr(self, "page", None)
        if page is None:
            return
        message = self._outage_text(kind, status)
        if not self._outage_notified:
            self._outage_notified = True
            try:
                page.show_dialog(
                    SnackBar(
                        content=Text(message),
                        behavior=SnackBarBehavior.FLOATING,
                        bgcolor=Colors.RED,
                    )
                )
            except Exception as e:
                self._lg.debug(f"Outage snack deferred: {e}")
        if not self._wallpapers and self._outage_tile is None:
            self._outage_tile = Container(
                padding=12,
                content=Column(
                    alignment=MainAxisAlignment.CENTER,
                    controls=[
                        Icon(
                            Icons.CLOUD_OFF,
                            size=48,
                            color=Colors.OUTLINE_VARIANT,
                        ),
                        Text(message, size=14),
                        FilledButton(
                            "Retry",
                            icon=Icons.REFRESH,
                            on_click=self.retry_now,
                        ),
                    ],
                ),
            )
            self.controls.append(self._outage_tile)
            try:
                self.update()
            except Exception as e:
                self._lg.debug(f"Outage tile update deferred: {e}")

    def _hide_outage(self) -> None:
        """Drop the outage tile and reset notification state."""
        self._outage_kind = None
        self._outage_notified = False
        self._poll_scheduled = False
        if self._outage_tile is not None:
            try:
                self.controls.remove(self._outage_tile)
            except ValueError:
                pass
            self._outage_tile = None

    def retry_now(self, e=None) -> None:
        """Manual retry from the outage placeholder button."""
        self._transient_failures = 0
        self._outage_notified = False
        self._poll_scheduled = False
        page = getattr(self, "page", None)
        if page is None:
            return
        page.run_task(self.load_more)

    async def _poll_with_delay(self, delay: float) -> None:
        """Slow re-poll while the grid is still empty after an outage."""
        await asyncio.sleep(delay)
        self._poll_scheduled = False
        if not self._wallpapers and self.has_more:
            await self.load_more()

    def _schedule_poll(self) -> None:
        """Schedule one slow re-poll if the grid is empty."""
        if self._poll_scheduled or self._wallpapers:
            return
        page = getattr(self, "page", None)
        if page is None:
            return
        self._poll_scheduled = True
        page.run_task(self._poll_with_delay, self.OUTAGE_POLL_DELAY)

    @staticmethod
    def _is_transient_error(exc: Exception) -> bool:
        """Check the HTTP status instead of parsing the message text.

        Only errors carrying a response with a status from
        WallhavenAPI.TRANSIENT_STATUSES are retried; anything else
        (including errors without a response) is logged as-is and
        never string-matched. Pagination (has_more) is left untouched
        on every error path.
        """
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
        return status in WallhavenAPI.TRANSIENT_STATUSES

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
                # Fire-and-forget: leave the cache empty, the explicit
                # load retries on its own. has_more stays untouched —
                # only a successful empty page ends pagination.
                self._lg.debug(f"Prefetch of page {page} skipped: {e}")
                return
            if generation != self._generation:
                return
            # Only reachable on a successful (200) empty page: API
            # errors raise instead of returning [].
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
        bus.publish(
            getattr(self, "page", None),
            bus.TOPIC_PREVIEW,
            {"wallpaper": wallpaper, "index": index},
        )

    def handle_image_double_click(self, e) -> None:
        """Show the resolution chooser for the double-clicked wallpaper.

        Args:
            e: Double tap event; the control data holds the cache index.
        """
        index = e.control.data
        wallpaper = self._wallpapers[index]
        self._lg.debug(f"Download requested for index - {index}.")
        bus.publish(
            getattr(self, "page", None),
            bus.TOPIC_DOWNLOAD_REQUEST,
            {"wallpaper": wallpaper},
        )