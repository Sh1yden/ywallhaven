"""Windows desktop wallpaper installer (Wave 1, T2).

All Win32 logic lives here behind a ``sys.platform`` gate, so this
module imports safely on Linux/macOS (where the "Set as Wallpaper"
button is hidden entirely). The UI layer only calls
:func:`set_wallpaper_from_url` and shows the returned ``(ok, message)``
pair via ``flet_app._show_snack``.

Temp file policy: a single fixed file ``TEMP/ywallhaven-wallpaper.jpg``
is overwritten on every install and never deleted right after applying
(Windows requires the path to stay alive). It is removed only by
:func:`cleanup_temp`, which the application shutdown routine calls.
"""

import asyncio
import ctypes
import sys
from io import BytesIO
from pathlib import Path
from tempfile import gettempdir
from typing import Awaitable, Callable

from PIL import Image as PILImage

from app.core import get_logger

_lg = get_logger()

SPI_SETDESKWALLPAPER = 20
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDCHANGE = 0x02

WALLPAPER_TEMP_NAME = "ywallhaven-wallpaper.jpg"
RATIO_TOLERANCE = 0.01


def is_supported() -> bool:
    """Return True only on Windows (the Win32 wallpaper API).

    Returns:
        True when ``sys.platform`` is ``win32``.
    """
    return sys.platform == "win32"


def temp_path() -> Path:
    """Return the fixed temp path for the wallpaper JPG.

    Returns:
        ``TEMP/ywallhaven-wallpaper.jpg`` path (overwritten each time).
    """
    return Path(gettempdir()) / WALLPAPER_TEMP_NAME


def get_screen_size() -> tuple[int, int] | None:
    """Return the physical monitor size via ctypes GetSystemMetrics.

    Uses the OS metric (SM_CXSCREEN/SM_CYSCREEN), not ``page.window``.

    Returns:
        (width, height) on Windows, or None when unavailable.
    """
    if not is_supported():
        return None
    try:
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        width = user32.GetSystemMetrics(0)
        height = user32.GetSystemMetrics(1)
    except Exception as e:
        _lg.error(f"Failed to read screen size: {e}.")
        return None
    if not width or not height:
        return None
    return (int(width), int(height))


def _to_jpg(image: PILImage.Image, quality: int) -> bytes:
    """Encode a Pillow image as JPEG bytes.

    Args:
        image: Source image (any mode; alpha is flattened).
        quality: JPEG quality for the output.

    Returns:
        JPEG-encoded bytes.
    """
    rgb = image.convert("RGB")
    output = BytesIO()
    rgb.save(output, format="JPEG", quality=quality)
    return output.getvalue()


def _looks_animated(data: bytes) -> bool:
    """Check whether the bytes are an animated image.

    Args:
        data: Original wallpaper file bytes.

    Returns:
        True for animated gif/webp, False otherwise (or on error).
    """
    try:
        with PILImage.open(BytesIO(data)) as image:
            return bool(getattr(image, "is_animated", False))
    except Exception:
        return False


def pick_or_resize(
    data: bytes, screen: tuple[int, int] | None
) -> bytes | None:
    """Return wallpaper bytes ready to write as JPG.

    Keeps the original file when its aspect ratio matches the monitor
    within ~0.01, otherwise downscales with PIL ``thumbnail`` (LANCZOS)
    — the same algorithm as ``flet_app._resize_image``. The output is
    always JPEG. Animated images (gif/webp) are refused with None.

    Args:
        data: Original wallpaper file bytes.
        screen: Monitor (width, height), or None when unknown.

    Returns:
        JPG bytes to install, or None when refused/impossible.
    """
    try:
        if screen is not None and (screen[0] <= 0 or screen[1] <= 0):
            screen = None
        image = PILImage.open(BytesIO(data))
        if getattr(image, "is_animated", False):
            return None
        if screen is not None:
            img_w, img_h = image.size
            if img_w > 0 and img_h > 0:
                ratio_match = (
                    abs(img_w / img_h - screen[0] / screen[1])
                    <= RATIO_TOLERANCE
                )
                if ratio_match:
                    if image.format == "JPEG" and image.mode == "RGB":
                        return data
                    return _to_jpg(image, quality=95)
            # Pillow 11: Image.LANCZOS removed -> Resampling.LANCZOS
            resampling = getattr(PILImage, "Resampling", None)
            lanczos = getattr(
                PILImage, "LANCZOS", getattr(resampling, "LANCZOS", 1)
            )
            image.thumbnail((screen[0], screen[1]), lanczos)
            return _to_jpg(image, quality=85)
        if image.format == "JPEG" and image.mode == "RGB":
            return data
        return _to_jpg(image, quality=95)
    except Exception as e:
        _lg.error(f"Failed to prepare wallpaper: {e}.")
        return None


def write_temp(data: bytes) -> Path | None:
    """Overwrite the fixed temp JPG with the given bytes.

    The file is intentionally NOT deleted here: Windows requires the
    wallpaper path to stay alive after ``SystemParametersInfoW``.

    Args:
        data: JPG bytes to store.

    Returns:
        Temp path on success, None on failure.
    """
    path = temp_path()
    try:
        path.write_bytes(data)
    except OSError as e:
        _lg.error(f"Failed to write wallpaper temp file {path}: {e}.")
        return None
    return path


def apply_wallpaper(path: Path) -> bool:
    """Point Windows at the given image path.

    Reference snippet (CHANGELOG): ``SystemParametersInfoW(20, 0, path,
    0x01 | 0x02)``.

    Args:
        path: Image file path to install as the desktop background.

    Returns:
        True when Windows accepted the new wallpaper.
    """
    if not is_supported():
        return False
    try:
        result = ctypes.windll.user32.SystemParametersInfoW(  # type: ignore[attr-defined]
            SPI_SETDESKWALLPAPER,
            0,
            str(path.resolve()),
            SPIF_UPDATEINIFILE | SPIF_SENDCHANGE,
        )
    except Exception as e:
        _lg.error(f"Failed to set wallpaper: {e}.")
        return False
    return bool(result)


def cleanup_temp() -> None:
    """Remove the temp wallpaper file (application shutdown only).

    Wired into the shutdown ``cleanup()`` routine; never called right
    after applying the wallpaper.
    """
    try:
        temp_path().unlink(missing_ok=True)
    except OSError as e:
        _lg.error(f"Failed to clean wallpaper temp file: {e}.")


async def set_wallpaper_from_url(
    fetch_bytes: Callable[[str], Awaitable[bytes | None]],
    url: str,
    screen: tuple[int, int] | None = None,
) -> tuple[bool, str]:
    """Download a wallpaper and install it as the desktop background.

    The bytes come from the existing API client
    (``middle_panel.api_client.fetch_bytes``) — no new long-lived
    ``AsyncClient`` is created here.

    Args:
        fetch_bytes: Awaitable downloader returning bytes or None.
        url: Full-size wallpaper URL.
        screen: Monitor size, or None to auto-detect via GetSystemMetrics.

    Returns:
        (ok, message) pair for the ``_show_snack`` call.
    """
    if not is_supported():
        return False, "Setting wallpaper is available on Windows only"
    if screen is None:
        screen = get_screen_size()
    _lg.info(f"Setting wallpaper from {url} (screen={screen}).")
    try:
        data = await fetch_bytes(url)
    except Exception as e:
        _lg.error(f"Failed to download wallpaper {url}: {e}.")
        return False, "Failed to download wallpaper"
    if not data:
        return False, "Failed to download wallpaper"
    prepared = await asyncio.to_thread(pick_or_resize, data, screen)
    if prepared is None:
        if _looks_animated(data):
            _lg.warning(f"Refused animated wallpaper {url}.")
            return False, "Animated images can't be set as wallpaper"
        return False, "Failed to prepare wallpaper"
    path = write_temp(prepared)
    if path is None:
        return False, "Failed to save wallpaper file"
    if not apply_wallpaper(path):
        return False, "Failed to set wallpaper"
    _lg.info(f"Wallpaper set from {url} ({len(prepared)} bytes).")
    return True, "Wallpaper set"
