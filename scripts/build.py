"""Build script: bake the version in and compile the executables.

Run with: ``uv run python scripts/build.py [--target win|linux]``.

Steps (Windows target):
1. Resolve the current version from the package metadata (hatch-vcs).
2. Generate ``app/core/_version.py`` with the resolved version.
3. Generate the Windows version info file ``build/version_info.txt``.
4. Convert ``docs/assets/icon.png`` to ``docs/assets/icon.ico``.
5. Build ``ywallhaven.exe`` and ``ywallhaven-updater.exe`` via PyInstaller.

Steps (Linux target):
1-2. Same version bake as Windows.
3. Skip the Windows-only version info and ``.ico`` icon.
4. Build the onedir ``dist/ywallhaven/`` folder plus the onefile
   ``dist/ywallhaven-updater`` helper via the ``*-linux.spec`` files.
   The folder layout is consumed by ``scripts/make_appdir.py``.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image as PILImage

ROOT = Path(__file__).resolve().parent.parent
VERSION_MODULE = ROOT / "app" / "core" / "_version.py"
VERSION_INFO = ROOT / "build" / "version_info.txt"
ICON_PNG = ROOT / "docs" / "assets" / "icon.png"
ICON_ICO = ROOT / "docs" / "assets" / "icon.ico"
WIN_SPECS = [
    ROOT / "ywallhaven.spec",
    ROOT / "ywallhaven-updater.spec",
]
LINUX_SPECS = [
    ROOT / "ywallhaven-linux.spec",
    ROOT / "ywallhaven-updater-linux.spec",
]
ENTRY = ROOT / "run.py"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the build target flag.

    Args:
        argv: Argument list (defaults to ``sys.argv``).

    Returns:
        Parsed namespace with the ``target`` attribute.
    """
    parser = argparse.ArgumentParser(description="Build ywallhaven.")
    parser.add_argument(
        "--target",
        choices=("auto", "win", "linux"),
        default="auto",
        help="win: .exe pair; linux: onedir folder + helper ELF.",
    )
    return parser.parse_args(argv)


def resolve_target(requested: str) -> str:
    """Map the requested target to a concrete one.

    Args:
        requested: ``auto``, ``win`` or ``linux``.

    Returns:
        ``win`` or ``linux``.
    """
    if requested == "auto":
        return "win" if sys.platform == "win32" else "linux"
    return requested


def resolve_version() -> str:
    """Resolve the current application version from sources.

    Returns:
        Version string like ``0.5.0`` or ``0.4.2.dev1``.
    """
    try:
        from app.core.version import __version__

        return __version__
    except Exception as e:
        print(f"Version resolve failed ({e}), fallback to git describe", file=sys.stderr)
        # Fallback when the environment is not yet synced.
        result = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        tag = result.stdout.strip().lstrip("v")
        return tag or "0.0.0"


def write_version_module(version: str) -> None:
    """Write the version module consumed by ``app.core.version``.

    Args:
        version: Version string to bake into the executable.
    """
    VERSION_MODULE.write_text(
        f'"""Generated at build time. Do not edit."""\n'
        f'__version__ = "{version}"\n',
        encoding="utf-8",
    )


def write_version_info(version: str) -> None:
    """Generate the PyInstaller Windows version info file.

    Args:
        version: Version string to inject into file properties.
    """
    segments = [part for part in re.split(r"[.\-+]", version) if part.isdigit()]
    segments = segments[:4]
    segments.extend(["0"] * (4 - len(segments)))
    filevers = tuple(int(part) for part in segments)

    VERSION_INFO.parent.mkdir(exist_ok=True)
    VERSION_INFO.write_text(
        "VSVersionInfo(\n"
        "  ffi=FixedFileInfo(\n"
        f"    filevers={filevers},\n"
        f"    prodvers={filevers},\n"
        "    mask=0x3f,\n"
        "    flags=0x0,\n"
        "    OS=0x40004,\n"
        "    fileType=0x1,\n"
        "    subtype=0x0,\n"
        "    date=(0, 0)\n"
        "  ),\n"
        "  kids=[\n"
        "    StringFileInfo([\n"
        "      StringTable('040904B0', [\n"
        "        StringStruct('CompanyName', 'ywallhaven'),\n"
        "        StringStruct('FileDescription', 'ywallhaven'),\n"
        f"        StringStruct('FileVersion', '{version}'),\n"
        "        StringStruct('InternalName', 'ywallhaven'),\n"
        f"        StringStruct('ProductVersion', '{version}'),\n"
        "        StringStruct('ProductName', 'ywallhaven'),\n"
        "        StringStruct('OriginalFilename', 'ywallhaven.exe')\n"
        "      ])\n"
        "    ]),\n"
        "    VarFileInfo([VarStruct('Translation', [1033, 1200])])\n"
        "  ]\n"
        ")\n",
        encoding="utf-8",
    )


def ensure_icon_ico() -> None:
    """Convert the bundled PNG icon to a Windows .ico if missing.

    PyInstaller needs an ``.ico`` for the exe icon; the generated file is
    also bundled as data so the running app can set the window icon.
    """
    if ICON_ICO.exists():
        return
    if not ICON_PNG.is_file():
        sys.exit(f"Missing source icon: {ICON_PNG}")
    with PILImage.open(ICON_PNG) as img:
        img.save(ICON_ICO, format="ICO")
    print(f"Generated {ICON_ICO.relative_to(ROOT)}")


def run_pyinstaller(spec: Path) -> None:
    """Run PyInstaller once for the given spec file.

    Args:
        spec: Spec file path (must exist).
    """
    if not spec.is_file():
        sys.exit(f"Missing spec file: {spec}")
    print(f"==> pyinstaller {spec.name}")
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", str(spec)],
        cwd=ROOT,
    )
    if result.returncode != 0:
        sys.exit(f"PyInstaller failed for {spec.name}")


def check_entry() -> None:
    """Fail early when the PyInstaller entry script is missing."""
    if not ENTRY.is_file():
        sys.exit(f"Missing entry script: {ENTRY} (spec files need it)")


def build_win() -> None:
    """Run the Windows build pipeline (.exe pair)."""
    check_entry()
    for spec in WIN_SPECS:
        run_pyinstaller(spec)

    dist = ROOT / "dist"
    print("\nBuild finished:")
    for name in ("ywallhaven.exe", "ywallhaven-updater.exe"):
        path = dist / name
        if not path.is_file():
            sys.exit(f"Missing build artifact: {path}")
        print(f"  - {path} ({path.stat().st_size / 1024 / 1024:.1f} MB)")


def build_linux() -> None:
    """Run the Linux build pipeline (onedir + helper ELF)."""
    check_entry()
    for spec in LINUX_SPECS:
        run_pyinstaller(spec)

    dist = ROOT / "dist"
    main_binary = dist / "ywallhaven" / "ywallhaven"
    helper = dist / "ywallhaven-updater"
    print("\nBuild finished:")
    for path in (main_binary, helper):
        if not path.is_file():
            sys.exit(f"Missing build artifact: {path}")
        print(f"  - {path} ({path.stat().st_size / 1024 / 1024:.1f} MB)")


def build(target: str) -> None:
    """Run the whole build pipeline for the given target.

    Args:
        target: ``win`` or ``linux``.
    """
    version = resolve_version()
    print(f"Building version {version} (target={target})")

    write_version_module(version)
    print(f"Generated {VERSION_MODULE.relative_to(ROOT)}")

    if target == "win":
        write_version_info(version)
        print(f"Generated {VERSION_INFO.relative_to(ROOT)}")
        ensure_icon_ico()
        build_win()
    else:
        build_linux()


def main(argv: list[str] | None = None) -> None:
    """Entry point parsing the target flag and building.

    Args:
        argv: Argument list (defaults to ``sys.argv``).
    """
    args = parse_args(argv)
    build(resolve_target(args.target))


if __name__ == "__main__":
    main()
