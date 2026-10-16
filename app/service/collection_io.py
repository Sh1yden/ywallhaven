"""Collection download helpers: bytes resolving and zip building.

Pure logic for the "download whole collection" flow; the dialog and
the save picker live in ``flet_app``. HTTP wallpapers go through the
API client fetcher, local files are read from disk. Failures never
raise — they are collected and reported at the end.
"""

import asyncio
import io
import zipfile
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List


def unique_name(taken: set, base: str) -> str:
    """Return a file name unused in the taken set, adding suffixes.

    Args:
        taken: Already used names (mutated in place).
        base: Desired file name.

    Returns:
        Unique file name like ``w.jpg`` or ``w(1).jpg``.
    """
    if base not in taken:
        taken.add(base)
        return base
    stem = Path(base).stem
    suffix = Path(base).suffix
    index = 1
    while True:
        candidate = f"{stem}({index}){suffix}"
        if candidate not in taken:
            taken.add(candidate)
            return candidate
        index += 1


def display_name(wallpaper: Dict[str, Any], index: int) -> str:
    """Build a file name for a wallpaper of any source.

    Args:
        wallpaper: Wallpaper dict (remote or local).
        index: Fallback position used when nothing else fits.

    Returns:
        File name with an extension.
    """
    path = str(wallpaper.get("path", ""))
    if path.startswith("http"):
        from app.service.wallhaven_api import WallhavenAPI

        return WallhavenAPI.build_filename(wallpaper)
    name = Path(path).name
    if name:
        return name
    return f"wallpaper-{index}.jpg"


async def resolve_bytes(
    wallpaper: Dict[str, Any],
    fetch: Callable[[str], Awaitable[bytes | None]],
) -> bytes | None:
    """Return file bytes of a wallpaper, remote or local.

    Args:
        wallpaper: Wallpaper dict with a ``path`` field.
        fetch: Async downloader for HTTP urls.

    Returns:
        File bytes, or None on any failure.
    """
    path = str(wallpaper.get("path", ""))
    if not path:
        return None
    if path.startswith("http"):
        try:
            return await fetch(path)
        except Exception:
            return None

    def _read() -> bytes | None:
        try:
            return Path(path).read_bytes()
        except OSError:
            return None

    return await asyncio.to_thread(_read)


async def build_zip(
    wallpapers: List[Dict[str, Any]],
    fetch: Callable[[str], Awaitable[bytes | None]],
    progress: Callable[[int, int], None] | None = None,
) -> tuple[bytes | None, List[str]]:
    """Pack wallpapers into a zip archive in memory.

    Args:
        wallpapers: Wallpaper dicts to pack.
        fetch: Async downloader for HTTP urls.
        progress: Optional callback receiving (done, total).

    Returns:
        (zip bytes or None when empty/all failed, failed ids).
    """
    taken: set = set()
    failed: List[str] = []
    buffer = io.BytesIO()
    done = 0
    total = len(wallpapers)
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for position, wallpaper in enumerate(wallpapers):
            data = await resolve_bytes(wallpaper, fetch)
            done += 1
            if progress is not None:
                progress(done, total)
            if not data:
                failed.append(str(wallpaper.get("id", "?")))
                continue
            archive.writestr(
                unique_name(taken, display_name(wallpaper, position)),
                data,
            )
    if not taken:
        return None, failed
    return buffer.getvalue(), failed
