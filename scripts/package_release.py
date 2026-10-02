"""Package a portable release: zip folder plus SHA256 checksums.

Reads the executables built by scripts/build.py from dist/, stages
them into dist/ywallhaven/, archives dist/ywallhaven_portable-<tag>.zip
(the zip keeps the ywallhaven/ folder inside) and writes
dist/SHA256SUMS.txt with hashes of both executables and the zip.

The plain .exe assets stay published alongside the zip so installed
updaters (which look for exactly "ywallhaven.exe") keep working.

Usage:
    uv run python scripts/package_release.py v0.11.0
"""

import hashlib
import shutil
import sys
from pathlib import Path

EXE_NAMES = ("ywallhaven.exe", "ywallhaven-updater.exe")
FOLDER_NAME = "ywallhaven"


def _find_exe(dist: Path, name: str) -> Path:
    """Locate a built executable, tolerating a missing .exe suffix."""
    candidate = dist / name
    if candidate.is_file():
        return candidate
    fallback = dist / Path(name).stem
    if fallback.is_file():
        return fallback
    raise FileNotFoundError(f"Built executable missing: {candidate}")


def _sha256(path: Path) -> str:
    """Return the hex SHA-256 of a file."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package(dist: Path, tag: str) -> dict:
    """Stage, zip and hash a portable release.

    Args:
        dist: Build output directory with both executables.
        tag: Release tag used in the zip file name.

    Returns:
        Mapping with the zip path and the checksums file path.
    """
    tag = tag.strip() or "untagged"
    stage = dist / FOLDER_NAME
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    staged = []
    for name in EXE_NAMES:
        src = _find_exe(dist, name)
        dst = stage / src.name
        shutil.copy2(src, dst)
        staged.append(dst)

    zip_path = dist / f"ywallhaven_portable-{tag}.zip"
    if zip_path.exists():
        zip_path.unlink()
    shutil.make_archive(
        str(zip_path.with_suffix("")),
        "zip",
        root_dir=str(dist),
        base_dir=FOLDER_NAME,
    )

    sums_path = dist / "SHA256SUMS.txt"
    lines = []
    for path in [*staged, zip_path]:
        lines.append(f"{_sha256(path)}  {path.name}")
    sums_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Portable zip: {zip_path}")
    print(f"Checksums: {sums_path}")
    return {"zip": zip_path, "sums": sums_path}


def main(argv: list) -> int:
    """Run the packager from the command line."""
    if len(argv) != 2:
        print("Usage: package_release.py <tag>", file=sys.stderr)
        return 2
    dist = Path("dist")
    try:
        package(dist, argv[1])
    except FileNotFoundError as e:
        print(f"package_release: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
