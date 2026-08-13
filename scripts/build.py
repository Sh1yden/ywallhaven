"""Build script: bake the version in and compile both executables.

Run with: ``uv run python scripts/build.py``.

Steps:
1. Resolve the current version from the package metadata (hatch-vcs).
2. Generate ``app/core/_version.py`` with the resolved version.
3. Generate the Windows version info file ``build/version_info.txt``.
4. Build ``ywallhaven.exe`` and ``ywallhaven-updater.exe`` via PyInstaller.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_MODULE = ROOT / "app" / "core" / "_version.py"
VERSION_INFO = ROOT / "build" / "version_info.txt"
SPECS = [
    ROOT / "ywallhaven.spec",
    ROOT / "ywallhaven-updater.spec",
]


def resolve_version() -> str:
    """Resolve the current application version from sources.

    Returns:
        Version string like ``0.5.0`` or ``0.4.2.dev1``.
    """
    try:
        from app.core.version import __version__

        return __version__
    except Exception:
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


def build() -> None:
    """Run the whole build pipeline."""
    version = resolve_version()
    print(f"Building version {version}")

    write_version_module(version)
    print(f"Generated {VERSION_MODULE.relative_to(ROOT)}")

    write_version_info(version)
    print(f"Generated {VERSION_INFO.relative_to(ROOT)}")

    for spec in SPECS:
        if not spec.is_file():
            sys.exit(f"Missing spec file: {spec}")
        print(f"==> pyinstaller {spec.name}")
        result = subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--noconfirm", str(spec)],
            cwd=ROOT,
        )
        if result.returncode != 0:
            sys.exit(f"PyInstaller failed for {spec.name}")

    dist = ROOT / "dist"
    suffix = ".exe" if sys.platform == "win32" else ""
    print("\nBuild finished:")
    for name in ("ywallhaven", "ywallhaven-updater"):
        path = dist / f"{name}{suffix}"
        if not path.exists():
            sys.exit(f"Missing build artifact: {path}")
        print(f"  - {path} ({path.stat().st_size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    build()