"""Assemble an AppDir tree from a Linux onedir build.

Reads the PyInstaller output in ``dist/`` (``dist/ywallhaven/`` folder
plus the ``dist/ywallhaven-updater`` helper) and stages
``dist/AppDir/`` for ``appimagetool``:

    dist/AppDir/
      AppRun                      (launches usr/bin/ywallhaven/ywallhaven)
      ywallhaven.desktop
      ywallhaven.png
      usr/bin/ywallhaven/         (onedir content: binary + _internal)
      usr/bin/ywallhaven/ywallhaven-updater

The updater helper sits next to the main binary on purpose: the
update flow resolves it as ``exe_path.parent / helper`` and, once
running from an AppImage, replaces the file pointed at by ``$APPIMAGE``.

Usage:
    uv run python scripts/make_appdir.py
"""

import shutil
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
APPDIR = DIST / "AppDir"
ICON_PNG = ROOT / "docs" / "assets" / "icon.png"

APP_NAME = "ywallhaven"
MAIN_DIR_NAME = "ywallhaven"
MAIN_BINARY_NAME = "ywallhaven"
HELPER_NAME = "ywallhaven-updater"
DESKTOP_NAME = "ywallhaven.desktop"
ICON_NAME = "ywallhaven.png"

APPRUN = """#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/ywallhaven/ywallhaven" "$@"
"""

DESKTOP = """[Desktop Entry]
Name=ywallhaven
Exec=ywallhaven
Icon=ywallhaven
Type=Application
Categories=Graphics;
Comment=Browse and download wallpapers from Wallhaven
StartupWMClass=ywallhaven
"""

REQUIRED_DESKTOP_KEYS = (
    "[Desktop Entry]",
    "Name=",
    "Exec=",
    "Icon=",
    "Type=Application",
)


def _fresh_dir(path: Path) -> Path:
    """Recreate an empty directory, removing leftovers first."""
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def _check_dist(dist: Path) -> tuple[Path, Path]:
    """Locate the onedir folder and the helper ELF in dist.

    Args:
        dist: Build output directory.

    Returns:
        (onedir folder, helper file) pair.

    Raises:
        FileNotFoundError: When either artifact is missing (hint: run
            ``scripts/build.py --target linux`` first).
    """
    folder = dist / MAIN_DIR_NAME
    binary = folder / MAIN_BINARY_NAME
    helper = dist / HELPER_NAME
    missing = [
        str(p) for p in (binary, helper) if not p.is_file()
    ]
    if missing:
        raise FileNotFoundError(
            "Linux build artifacts missing "
            f"({', '.join(missing)}); run "
            "scripts/build.py --target linux first."
        )
    return folder, helper


def _write_text(path: Path, content: str, executable: bool = False) -> Path:
    """Write a text file, optionally marking it executable."""
    path.write_text(content, encoding="utf-8")
    if executable:
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _copy_tree(src: Path, dst: Path) -> None:
    """Copy a directory tree preserving symlinks (Flet ships some)."""
    shutil.copytree(src, dst, symlinks=True)


def validate_desktop(content: str) -> list[str]:
    """Return the list of missing required desktop entry keys."""
    return [key for key in REQUIRED_DESKTOP_KEYS if key not in content]


def build_appdir(
    dist: Path = DIST, icon_png: Path = ICON_PNG
) -> dict[str, Path]:
    """Stage the AppDir tree from a Linux build.

    Args:
        dist: Directory with the PyInstaller Linux output.
        icon_png: Source application icon (PNG).

    Returns:
        Mapping with the ``appdir``, ``apprun``, ``desktop``,
        ``icon``, ``main`` and ``helper`` paths.

    Raises:
        FileNotFoundError: When the build output or icon is missing.
        ValueError: When the desktop template loses a required key.
    """
    folder, helper_src = _check_dist(dist)
    if not icon_png.is_file():
        raise FileNotFoundError(f"Missing icon: {icon_png}")

    missing_keys = validate_desktop(DESKTOP)
    if missing_keys:
        raise ValueError(f"Desktop entry lacks keys: {missing_keys}")

    appdir = _fresh_dir(dist / "AppDir")
    bin_target = appdir / "usr" / "bin" / MAIN_DIR_NAME
    bin_target.parent.mkdir(parents=True, exist_ok=True)
    _copy_tree(folder, bin_target)

    helper_dst = bin_target / HELPER_NAME
    shutil.copy2(helper_src, helper_dst)
    for binary in (bin_target / MAIN_BINARY_NAME, helper_dst):
        mode = binary.stat().st_mode
        binary.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    apprun = _write_text(appdir / "AppRun", APPRUN, executable=True)
    desktop = _write_text(appdir / DESKTOP_NAME, DESKTOP)
    icon = appdir / ICON_NAME
    shutil.copy2(icon_png, icon)

    print(f"AppDir staged: {appdir}")
    return {
        "appdir": appdir,
        "apprun": apprun,
        "desktop": desktop,
        "icon": icon,
        "main": bin_target / MAIN_BINARY_NAME,
        "helper": helper_dst,
    }


def main(argv: list[str]) -> int:
    """Run the AppDir stager from the command line."""
    if len(argv) != 1:
        print("Usage: make_appdir.py", file=sys.stderr)
        return 2
    try:
        build_appdir()
    except (FileNotFoundError, ValueError, OSError) as e:
        print(f"make_appdir: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
