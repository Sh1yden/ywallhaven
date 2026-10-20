"""Collection download helpers: bytes resolving and zip building.

Pure logic for the "download whole collection" flow; the dialog and
the save picker live in ``flet_app``. HTTP wallpapers go through the
API client fetcher, local files are read from disk. Failures never
raise — they are collected and reported at the end.
"""

import asyncio
import zipfile
from pathlib import Path
from typing import Any, Awaitable, BinaryIO, Callable, Dict, List

from app.core import get_logger

_lg = get_logger()


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
    sink: BinaryIO,
    wallpapers: List[Dict[str, Any]],
    fetch: Callable[[str], Awaitable[bytes | None]],
    progress: Callable[[int, int], None] | None = None,
) -> tuple[bool, List[str]]:
    """Pack wallpapers into a zip archive streamed to ``sink``.

    The archive is written entry by entry straight into the sink, so
    the whole zip never sits in memory: desktop passes an open file,
    mobile/web pass a ``BytesIO`` whose bytes go to the file picker.
    Local wallpapers are added from disk without loading them, remote
    ones travel through the API fetcher. The sink must be seekable
    (zipfile patches headers) and stays open — its owner decides
    whether to keep or delete the result.

    Args:
        sink: Seekable binary stream receiving the archive bytes.
        wallpapers: Wallpaper dicts to pack.
        fetch: Async downloader for HTTP urls.
        progress: Optional callback receiving (done, total).

    Returns:
        (ok, failed ids); ok is False when nothing was packed or the
        stream failed, so the caller drops the (partial) target.
    """
    taken: set = set()
    failed: List[str] = []
    done = 0
    packed = 0
    total = len(wallpapers)

    def _add_bytes(archive: zipfile.ZipFile, data: bytes, name: str) -> None:
        archive.writestr(name, data)

    def _add_local(
        archive: zipfile.ZipFile, source: Path, name: str
    ) -> None:
        archive.write(source, arcname=name)

    try:
        with zipfile.ZipFile(sink, "w", zipfile.ZIP_DEFLATED) as archive:
            for position, wallpaper in enumerate(wallpapers):
                path = str(wallpaper.get("path", ""))
                written = False
                if path.startswith("http"):
                    data = await resolve_bytes(wallpaper, fetch)
                    if data:
                        name = unique_name(
                            taken, display_name(wallpaper, position)
                        )
                        # Compression runs in a worker thread, so the
                        # event loop keeps serving UI updates.
                        await asyncio.to_thread(
                            _add_bytes, archive, data, name
                        )
                        written = True
                elif path:
                    # Local files stream from disk: zipfile reads them
                    # itself, so no full copy ever enters memory.
                    source = Path(path)
                    if source.is_file():
                        name = unique_name(
                            taken, display_name(wallpaper, position)
                        )
                        try:
                            await asyncio.to_thread(
                                _add_local, archive, source, name
                            )
                            written = True
                        except (
                            FileNotFoundError,
                            PermissionError,
                            IsADirectoryError,
                        ) as e:
                            # Failed before any bytes were archived.
                            _lg.debug(
                                f"Skipped local wallpaper "
                                f"{source}: {e}."
                            )
                if written:
                    packed += 1
                else:
                    failed.append(str(wallpaper.get("id", "?")))
                done += 1
                if progress is not None:
                    progress(done, total)
    except Exception as e:
        _lg.error(f"Failed to build zip archive: {e}.")
        return False, failed
    return packed > 0, failed
