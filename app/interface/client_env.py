"""Sanitize the environment of the external Flet view client.

Frozen Linux builds run with ``LD_LIBRARY_PATH`` pointing at the
PyInstaller bundle (``.../_internal``), which also ships a desktop
GUI stack pulled in via the Flutter engine closure. The Flet view
client (``~/.flet/client``) is a separate process launched with a
plain copy of our environment, so it resolves those older bundled
copies instead of the system ones and dies instantly with errors
like ``undefined symbol: g_once_init_enter_pointer`` — without any
log of its own.

The fix scrubs bundle entries out of ``LD_LIBRARY_PATH`` for the
view client only (via the ``flet_desktop`` launch seam). Our own
process keeps resolving its bundled libs untouched, so in-process
imports (TLS, Pillow codecs, sqlite) cannot regress.
"""

import functools
import sys
from typing import Any

from app.core import get_logger

_lg = get_logger()

_BUNDLE_MARKERS = ("_internal", "_MEI")


def scrub_bundle_lib_paths(env: dict) -> dict:
    """Copy an env mapping minus PyInstaller bundle library paths.

    Args:
        env: Environment mapping (e.g. for a child process).

    Returns:
        Copy with bundle entries removed from ``LD_LIBRARY_PATH``;
        the variable itself is dropped when nothing remains.
    """
    cleaned = dict(env)
    raw = cleaned.get("LD_LIBRARY_PATH", "")
    kept = [
        part
        for part in raw.split(":")
        if part and not any(mark in part for mark in _BUNDLE_MARKERS)
    ]
    if kept:
        cleaned["LD_LIBRARY_PATH"] = ":".join(kept)
    else:
        cleaned.pop("LD_LIBRARY_PATH", None)
    return cleaned


def patch_flet_client_env() -> bool:
    """Scrub bundle lib paths from the Flet view client environment.

    Wraps ``flet_desktop.__locate_and_unpack_flet_view`` once so the
    launched desktop client never sees the frozen bundle paths.
    No-op unless running frozen (i.e. only inside the packaged app).

    Returns:
        True when the seam was patched, False otherwise.
    """
    if not getattr(sys, "frozen", False):
        return False
    try:
        import flet_desktop
    except ImportError as e:
        _lg.debug(f"Flet client env patch skipped: {e}.")
        return False
    locate = getattr(
        flet_desktop, "__locate_and_unpack_flet_view", None
    )
    if locate is None or getattr(locate, "_yw_patched", False):
        return False

    @functools.wraps(locate)
    def _wrapper(*args: Any, **kwargs: Any):  # type: ignore[no-untyped-def]
        cmd, env, pid_file = locate(*args, **kwargs)
        return cmd, scrub_bundle_lib_paths(env), pid_file

    _wrapper._yw_patched = True  # type: ignore[attr-defined]
    flet_desktop.__locate_and_unpack_flet_view = _wrapper
    _lg.debug("Flet client env patched (bundle lib paths scrubbed).")
    return True
