"""Tests for the Linux spec GUI-stack exclusion list.

The PyInstaller bootloader exports LD_LIBRARY_PATH at the bundle, so
any shipped GTK/X11 copy shadows the system one for the externally
launched Flet view client (undefined-symbol crash). This guards the
exclusion list in ywallhaven-linux.spec: desktop libs must match,
runtime libs our process needs must not.
"""

import re
from pathlib import Path

SPEC = (
    Path(__file__).resolve().parent.parent / "ywallhaven-linux.spec"
)

# Native libs the frozen process needs at runtime (must be kept).
MUST_KEEP = (
    "libssl.so.3",
    "libcrypto.so.3",
    "libjpeg.so.62",
    "libpng16.so.16",
    "libfreetype.so.6",
    "libfontconfig.so.1",
    "libpython3.13.so.1.0",
    "libsqlite3.so.0",
    "libstdc++.so.6",
    "libwebp.so.7",
)

# Desktop/GUI libs that must never ship (shadow system ones).
MUST_DROP = (
    "libgtk-3.so.0",
    "libgdk-3.so.0",
    "libglib-2.0.so.0",
    "libgobject-2.0.so.0",
    "libgio-2.0.so.0",
    "libcairo.so.2",
    "libpango-1.0.so.0",
    "libX11.so.6",
    "libxcb.so.1",
    "libdbus-1.so.3",
    "libsystemd.so.0",
    "libicudata.so.78",
    "libicuuc.so.78",
)


def _prefixes() -> tuple:
    """Extract exclusion prefixes from the spec file text."""
    text = SPEC.read_text(encoding="utf-8")
    found: list = []
    for name in ("GUI_LIB_PREFIXES", "EXTRA_DROP_PREFIXES"):
        match = re.search(
            rf"{name}\s*=\s*\((.*?)\)", text, re.DOTALL
        )
        assert match, f"{name} not found in linux spec"
        found.extend(re.findall(r'"([^"]+)"', match.group(1)))
    return tuple(found)


def _dropped(name: str, prefixes: tuple) -> bool:
    return name.startswith(prefixes)


def test_exclusion_list_exists():
    assert _prefixes()


def test_desktop_libs_are_dropped():
    prefixes = _prefixes()
    for name in MUST_DROP:
        assert _dropped(name, prefixes), f"{name} would ship"


def test_runtime_libs_are_kept():
    prefixes = _prefixes()
    for name in MUST_KEEP:
        assert not _dropped(name, prefixes), f"{name} would drop"


def test_duplicate_client_tree_excluded_from_datas():
    text = SPEC.read_text(encoding="utf-8")
    assert 'startswith("flet_desktop/app")' in text
