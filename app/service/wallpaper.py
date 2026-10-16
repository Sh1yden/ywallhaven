"""Desktop wallpaper installer with per-platform backends.

The UI layer only calls :func:`set_wallpaper_from_url` (or checks
:func:`is_supported`) and shows the returned ``(ok, message)`` pair
via ``flet_app._show_snack``. Platform differences live in small
backend classes behind :func:`_select_backend`, so this module
imports safely everywhere: ``ctypes.windll`` is touched only inside
the Windows backend, ``subprocess`` tools only inside the Linux one.

Backends:

- Windows: ``SystemParametersInfoW`` + physical monitor size via
  ``GetSystemMetrics`` (unchanged legacy behavior).
- Noctalia shell: ``noctalia msg wallpaper-set`` IPC (owns resize,
  transitions and palette, so it gets the untouched original file).
- Linux: desktop-environment cascade (GNOME ``gsettings``,
  KDE ``plasma-apply-wallpaperimage``/``qdbus``, XFCE
  ``xfconf-query``, fallback ``feh``/``nitrogen``). Screen size is
  reported as unknown (``None``), so images keep the
  passthrough/convert path instead of a wrong resize.
  ``gsettings`` is skipped on Wayland without GNOME (false success).
- Android and anything else: stub, always unavailable. The native
  Android wiring (``WallpaperManager``) is intentionally left for
  the future full Android client.

Temp file policy: a single fixed file ``TEMP/ywallhaven-wallpaper.jpg``
is overwritten on every install and never deleted right after applying
(the OS requires the path to stay alive). It is removed only by
:func:`cleanup_temp`, which the application shutdown routine calls.
"""

import asyncio
import ctypes
import os
import shutil
import subprocess
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

_SUBPROCESS_TIMEOUT = 15.0

_UNSUPPORTED_MESSAGE = (
    "Setting wallpaper is not supported on this platform"
)
_NO_TOOL_MESSAGE = (
    "No supported wallpaper tool found "
    "(gsettings, plasma-apply-wallpaperimage, qdbus, "
    "xfconf-query, feh, nitrogen)"
)


def is_supported() -> bool:
    """Return True on platforms with a wallpaper backend.

    Windows and Linux have real backends (Linux tries several
    desktop-environment tools at apply time). Android and other
    platforms report False and the UI hides the button there.

    Returns:
        True on ``win32`` and Linux, False elsewhere.
    """
    return _select_backend().supports


def temp_path() -> Path:
    """Return the fixed temp path for the wallpaper JPG.

    Returns:
        ``TEMP/ywallhaven-wallpaper.jpg`` path (overwritten each time).
    """
    return Path(gettempdir()) / WALLPAPER_TEMP_NAME


def get_screen_size() -> tuple[int, int] | None:
    """Return the physical monitor size, or None when unknown.

    Windows uses the OS metric (SM_CXSCREEN/SM_CYSCREEN), not
    ``page.window``. Linux reports None (no reliable toolkit-free
    probe), so images take the no-resize path.

    Returns:
        (width, height) on Windows, None elsewhere/unavailable.
    """
    if not is_supported():
        return None
    return _select_backend().screen_size()


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

    The file is intentionally NOT deleted here: the OS requires the
    wallpaper path to stay alive after applying it.

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
    """Point the desktop environment at the given image path.

    Args:
        path: Image file path to install as the desktop background.

    Returns:
        True when the OS accepted the new wallpaper.
    """
    if not is_supported():
        return False
    return _select_backend().apply(path)


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
        screen: Monitor size, or None to auto-detect per platform.

    Returns:
        (ok, message) pair for the ``_show_snack`` call.
    """
    if not is_supported():
        return False, _UNSUPPORTED_MESSAGE
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
    backend = _select_backend()
    if backend.wants_original:
        # Shells rendering the wallpaper themselves (own resize,
        # transitions, palette extraction) get the untouched file:
        # re-encoding would only lose quality or the format.
        if _looks_animated(data):
            _lg.warning(f"Refused animated wallpaper {url}.")
            return False, "Animated images can't be set as wallpaper"
        prepared = data
    else:
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
        return False, backend.fail_message
    _lg.info(f"Wallpaper set from {url} ({len(prepared)} bytes).")
    return True, "Wallpaper set"


# Backends --------------------------------------------------------


class _Backend:
    """Base class for per-platform wallpaper installers."""

    name = "unsupported"
    supports = False
    # Shells rendering the wallpaper themselves (own resize and
    # transitions) want the untouched original file.
    wants_original = False
    # Message for set_wallpaper_from_url when apply() fails.
    fail_message = "Failed to set wallpaper"

    def screen_size(self) -> tuple[int, int] | None:
        """Return the monitor size, or None when unknown."""
        return None

    def apply(self, path: Path) -> bool:
        """Install the image at path as the desktop background."""
        return False


class _WindowsBackend(_Backend):
    """Wallpaper installer via the Win32 desktop API."""

    name = "windows"
    supports = True

    def screen_size(self) -> tuple[int, int] | None:
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

    def apply(self, path: Path) -> bool:
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


class _LinuxBackend(_Backend):
    """Wallpaper installer for Linux desktop environments.

    Tries desktop-specific tools in an environment-aware order and
    stops at the first success. Every step is best-effort with a
    logged command line and exit code; nothing raises.
    """

    name = "linux"
    supports = True
    fail_message = _NO_TOOL_MESSAGE

    def apply(self, path: Path) -> bool:
        desktop = _detect_desktop()
        _lg.info(
            f"Setting Linux wallpaper (desktop={desktop or 'unknown'})."
        )
        for label, attempt in self._plan(path, desktop):
            try:
                if attempt():
                    _lg.info(f"Wallpaper set via {label}.")
                    return True
            except Exception as e:
                _lg.debug(f"Wallpaper attempt {label} raised: {e}.")
        _lg.warning(_NO_TOOL_MESSAGE + ".")
        return False

    def _plan(self, path: Path, desktop: str):
        """Order install attempts by detected desktop environment.

        ``gsettings`` without a GNOME-like session is skipped: it
        would "succeed" writing dconf with zero visible effect,
        which is worse than an honest failure.
        """
        gsettings = lambda: _apply_gsettings(path)  # noqa: E731
        kde = lambda: _apply_kde(path)  # noqa: E731
        xfce = lambda: _apply_xfce(path)  # noqa: E731
        fallback = lambda: _apply_fallback(path)  # noqa: E731
        gnome_like = any(
            key in desktop for key in ("gnome", "cinnamon", "unity", "budgie")
        )
        if "kde" in desktop or "plasma" in desktop:
            ordered = [
                ("plasma-apply/qdbus", kde),
                ("xfconf-query", xfce),
                ("feh/nitrogen", fallback),
            ]
        elif "xfce" in desktop:
            ordered = [
                ("xfconf-query", xfce),
                ("feh/nitrogen", fallback),
            ]
        else:
            ordered = [
                ("plasma-apply/qdbus", kde),
                ("xfconf-query", xfce),
                ("feh/nitrogen", fallback),
            ]
        if gnome_like:
            ordered.insert(0, ("gsettings", gsettings))
        elif not _is_wayland():
            # X11 last resort only: without a GNOME session it is
            # still able to paint on plain X desktops.
            ordered.append(("gsettings", gsettings))
        return ordered


class _NoctaliaBackend(_Backend):
    """Wallpaper installer via the Noctalia shell IPC.

    Noctalia renders wallpapers itself (own resize, transitions and
    palette extraction), so it receives the untouched original file
    (``wants_original``). Verified live against
    ``noctalia msg wallpaper-set <path>`` (no connector = all
    outputs; ``ALL`` is not a valid connector).
    """

    name = "noctalia"
    supports = True
    wants_original = True
    fail_message = "Failed to set wallpaper: Noctalia rejected it"

    def apply(self, path: Path) -> bool:
        proc = _run(
            ["noctalia", "msg", "wallpaper-set", str(path.resolve())],
            "noctalia",
        )
        return proc is not None


class _StubBackend(_Backend):
    """Placeholder for platforms without wallpaper support yet.

    Android lands here until the full Android client wires the
    native ``WallpaperManager`` calls.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.supports = False


def _select_backend() -> _Backend:
    """Return the wallpaper backend for the running platform."""
    platform = sys.platform
    if platform == "win32":
        return _WindowsBackend()
    if platform.startswith("linux"):
        if _is_noctalia_session():
            return _NoctaliaBackend()
        return _LinuxBackend()
    if platform == "android":
        return _StubBackend("android")
    return _StubBackend(platform)


def _is_wayland() -> bool:
    """Return True inside a Wayland session."""
    if os.environ.get("WAYLAND_DISPLAY"):
        return True
    return os.environ.get("XDG_SESSION_TYPE", "").strip().lower() == "wayland"


def _process_running(name: str) -> bool:
    """Check via /proc whether a process with the given name runs.

    Args:
        name: Process name to look for (comm or argv[0] basename).

    Returns:
        True when at least one matching process exists.
    """
    try:
        proc_dir = Path("/proc")
        if not proc_dir.is_dir():
            return False
        for pid in proc_dir.iterdir():
            if not pid.name.isdigit():
                continue
            try:
                comm = (pid / "comm").read_text().strip()
            except OSError:
                continue
            if comm == name:
                return True
    except OSError as e:
        _lg.debug(f"Process scan failed: {e}.")
        return False
    return False


def _is_noctalia_session() -> bool:
    """Return True when the Noctalia shell can take wallpapers.

    Requires the ``noctalia`` IPC client plus a running shell, so a
    stray binary without the session never hijacks the cascade.
    """
    if _which("noctalia") is None:
        return False
    return _process_running("noctalia")


def _detect_desktop() -> str:
    """Return a lowercase desktop-environment hint, or ''."""
    for var in ("XDG_CURRENT_DESKTOP", "DESKTOP_SESSION"):
        value = os.environ.get(var, "")
        if value:
            return value.strip().lower()
    return ""


def _which(binary: str) -> str | None:
    """Return the resolved path of a helper binary, or None."""
    found = shutil.which(binary)
    if found is None:
        _lg.debug(f"Wallpaper helper missing: {binary}.")
    return found


def _run(
    cmd: list[str], label: str
) -> subprocess.CompletedProcess | None:
    """Run a helper command without a shell, catching all errors.

    Args:
        cmd: Argument list (no shell expansion).
        label: Short name for log lines.

    Returns:
        CompletedProcess, or None when the binary is missing or
        the run itself failed.
    """
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
    except FileNotFoundError:
        _lg.debug(f"Wallpaper helper missing: {cmd[0]}.")
        return None
    except (OSError, subprocess.TimeoutExpired) as e:
        _lg.debug(f"Wallpaper attempt {label} failed: {e}.")
        return None
    if proc.returncode != 0:
        _lg.debug(
            f"Wallpaper attempt {label} exited "
            f"{proc.returncode}: {(proc.stderr or '').strip()}."
        )
        return None
    return proc


def _apply_gsettings(path: Path) -> bool:
    """Set the wallpaper on GNOME/Cinnamon via gsettings."""
    if _which("gsettings") is None:
        return False
    uri = path.resolve().as_uri()
    ok = False
    for key in ("picture-uri", "picture-uri-dark"):
        proc = _run(
            [
                "gsettings",
                "set",
                "org.gnome.desktop.background",
                key,
                uri,
            ],
            f"gsettings:{key}",
        )
        ok = proc is not None or ok
    return ok


def _apply_kde(path: Path) -> bool:
    """Set the wallpaper on KDE Plasma, if its tools exist."""
    target = str(path.resolve())
    applier = _which("plasma-apply-wallpaperimage")
    if applier is not None:
        return _run([applier, target], "plasma-apply") is not None
    if _which("qdbus") is None:
        return False
    script = (
        "for (const desktop of desktops()) {"
        "desktop.wallpaperPlugin = "
        "'org.kde.image';"
        f"desktop.currentConfigGroup = ['Wallpaper', "
        f"'org.kde.image', 'General'];"
        f"desktop.writeConfig('Image', 'file://{target}');"
        "}"
    )
    return (
        _run(
            [
                "qdbus",
                "org.kde.plasmashell",
                "/PlasmaShell",
                "org.kde.PlasmaShell.evaluateScript",
                script,
            ],
            "qdbus",
        )
        is not None
    )


def _apply_xfce(path: Path) -> bool:
    """Set the wallpaper on XFCE via xfconf-query."""
    if _which("xfconf-query") is None:
        return False
    target = str(path.resolve())
    listed = _run(
        ["xfconf-query", "-c", "xfce4-desktop", "-l"], "xfconf-list"
    )
    if listed is None:
        return False
    props = [
        line.strip()
        for line in (listed.stdout or "").splitlines()
        if line.strip().endswith("last-image")
    ]
    if not props:
        return False
    ok = False
    for prop in props:
        proc = _run(
            [
                "xfconf-query",
                "-c",
                "xfce4-desktop",
                "-p",
                prop,
                "-s",
                target,
            ],
            f"xfconf:{prop}",
        )
        ok = proc is not None or ok
    return ok


def _apply_fallback(path: Path) -> bool:
    """Set the wallpaper via feh/nitrogen on minimal window managers."""
    target = str(path.resolve())
    if _which("feh") is not None:
        if _run(["feh", "--bg-scale", target], "feh") is not None:
            return True
    if _which("nitrogen") is not None:
        if (
            _run(
                ["nitrogen", "--set-scaled", target], "nitrogen"
            )
            is not None
        ):
            return True
    return False
