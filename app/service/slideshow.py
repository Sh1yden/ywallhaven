"""Slideshow engine: rotate wallpapers on a timer.

Drives any wallpaper list (collection or scanned folder) through the
existing wallpaper installer. One engine per app session, owned by
``flet_app``; settings (interval, order) are read at start and on
every resync. Failures skip to the next item, never stopping the
loop — only an explicit stop does.
"""

import asyncio
import random
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List

from app.core import get_logger

_lg = get_logger()

MIN_INTERVAL = 10


def clamp_interval(value: Any) -> int:
    """Clamp a raw interval to a sane number of seconds.

    Args:
        value: Raw interval (anything int()-able).

    Returns:
        At least MIN_INTERVAL seconds (default 300 on garbage).
    """
    try:
        interval = int(value)
    except (ValueError, TypeError):
        return 300
    return max(MIN_INTERVAL, interval)


class SlideshowService:
    """Timer loop setting wallpapers from a list."""

    def __init__(
        self,
        apply: Callable[[Dict[str, Any]], Awaitable[bool]],
        paused: Callable[[], bool] | None = None,
    ) -> None:
        """Create a stopped engine.

        Args:
            apply: Async function applying one wallpaper dict,
                returning True on success.
            paused: Optional predicate skipping ticks (e.g. while
                fullscreen is open).
        """
        self._apply = apply
        self._paused = paused or (lambda: False)
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self.running = False
        self.label = ""

    @property
    def active(self) -> bool:
        """Return True while the loop task is alive."""
        return self._task is not None and not self._task.done()

    async def start(
        self,
        wallpapers: List[Dict[str, Any]],
        *,
        label: str,
        interval: Any,
        order: str = "sequential",
    ) -> bool:
        """Start rotating (restarts when already running).

        Args:
            wallpapers: Non-empty wallpaper list to rotate.
            label: Human name for logs (collection/folder name).
            interval: Seconds between switches (clamped).
            order: "sequential" or "random".

        Returns:
            True when started, False on an empty list.
        """
        await self.stop()
        if not wallpapers:
            return False
        self._stop.clear()
        self.running = True
        self.label = label
        self._task = asyncio.create_task(
            self._loop(
                list(wallpapers), clamp_interval(interval), order
            )
        )
        _lg.info(
            f"Slideshow started: {label} "
            f"({len(wallpapers)} items)."
        )
        return True

    async def stop(self) -> None:
        """Stop the loop and wait for the tick to finish."""
        self.running = False
        self._stop.set()
        task, self._task = self._task, None
        if task is not None and not task.done():
            try:
                await task
            except asyncio.CancelledError:
                pass
        self.label = ""

    async def _loop(
        self,
        wallpapers: List[Dict[str, Any]],
        interval: int,
        order: str,
    ) -> None:
        """Rotate until stopped, skipping failures and pauses."""
        position = 0
        while not self._stop.is_set():
            if self._paused():
                _lg.debug("Slideshow tick paused.")
            else:
                current, position = self._pick(
                    wallpapers, position, order
                )
                try:
                    ok = await self._apply(current)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    _lg.warning(f"Slideshow tick failed: {e}.")
                    ok = False
                if not ok:
                    _lg.debug("Slideshow tick skipped.")
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=interval
                )
            except asyncio.TimeoutError:
                pass

    @staticmethod
    def _pick(
        wallpapers: List[Dict[str, Any]], position: int, order: str
    ) -> tuple[Dict[str, Any], int]:
        """Pick the current item and the next position.

        Args:
            wallpapers: Rotation list (non-empty).
            position: Current sequential position.
            order: "sequential" or "random".

        Returns:
            (wallpaper, next position) pair.
        """
        if order == "random":
            return random.choice(wallpapers), position
        return wallpapers[position % len(wallpapers)], position + 1


def local_file_bytes(path: str) -> bytes | None:
    """Read a local image file, tolerating failures."""
    try:
        return Path(path).read_bytes()
    except OSError:
        return None
