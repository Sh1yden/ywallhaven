import asyncio
from typing import Any, Dict

from flet import (
    GridView,
    Container,
    Colors,
    ClipBehavior,
    Image,
    BoxFit,
    OnScrollEvent,
)
from app.core import LoggerMixin
from app.service import WallhavenAPI


class MiddlePanel(GridView, LoggerMixin):
    SCROLL_THRESHOLD = 300

    def __init__(self) -> None:
        super().__init__()
        self.api_client = WallhavenAPI()
        self.expand = 3
        self.runs_count = 4
        self.controls = []
        self.state_page = 1
        self.has_more = True

        self._load_lock = asyncio.Lock()
        self._in_trigger_zone = False

        self.on_scroll = self.handle_scroll

    def did_mount(self) -> None:
        super().did_mount()
        self.page.run_task(self.load_more)

    def will_unmount(self):
        super().will_unmount()
        self.page.run_task(self.api_client.close)

    async def load_more(self, *args) -> None:
        if not self.has_more:
            return

        if self._load_lock.locked():
            return

        async with self._load_lock:
            try:
                self._lg.debug(f"Loading page {self.state_page}...")

                wallpapers = await self.api_client.search_wallpapers(
                    page=self.state_page
                )

                if not wallpapers:
                    self._lg.warning("No more wallpapers found.")
                    self.has_more = False
                    return

                self.controls.extend(self._build_title(wp) for wp in wallpapers)
                self.state_page += 1
                self.update()
            except Exception as e:
                self._lg.critical(f"Internal error: {e}.")

    def _build_title(self, wallpaper: Dict[str, Any]) -> Container:
        thumb_url = wallpaper["thumbs"]["small"]
        full_url = wallpaper["path"]
        return Container(
            data=full_url,
            border_radius=8,
            bgcolor=Colors.GREY_500,
            clip_behavior=ClipBehavior.HARD_EDGE,
            content=Image(src=thumb_url, fit=BoxFit.COVER),
        )

    def handle_scroll(self, e: OnScrollEvent) -> None:
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
