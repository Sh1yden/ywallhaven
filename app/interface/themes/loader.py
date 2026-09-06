"""Loader for user-defined themes from ./themes/*.json."""

import json
import shutil
import sys
import tempfile
from pathlib import Path

from app.core import get_logger
from app.interface.themes.schema import ThemeDefinition

_lg = get_logger()

_USER_THEMES: dict[str, ThemeDefinition] = {}

_SEED_NAME_PREFIXES = ("readme",)
_SEED_NAME_SUFFIX = ".example"


def _bundled_themes_dir() -> Path | None:
    """Return the read-only themes dir bundled inside a frozen build.

    Only meaningful under PyInstaller onefile: ``sys._MEIPASS`` points at
    a temp extraction folder that is deleted once the process exits, so
    it must never be treated as the *persistent* user themes directory
    (that was the actual bug -- see ``_theme_dir``).

    Returns:
        Path to the bundled ``themes`` folder, or ``None`` when not
        running from a frozen build.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass) / "themes" if meipass else None


def _candidate_theme_dirs() -> tuple[Path, ...]:
    """Return candidate user-themes directories, in preference order.

    When frozen, the executable's own folder is checked first so
    imported themes persist across restarts and updates; the bundled
    ``_MEIPASS`` copy is listed last, purely as a read-only fallback,
    since writes there are lost the moment the process exits. In
    dev/tests (no ``_MEIPASS``), cwd comes first so ``tmp_path``-based
    tests keep working unchanged.

    Returns:
        Tuple of candidate paths, deduplicated, most preferred first.
    """
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        try:
            candidates.append(Path(sys.executable).resolve().parent / "themes")
        except Exception:
            pass
    try:
        candidates.append(Path.cwd() / "themes")
    except Exception:
        pass
    try:
        candidates.append(
            Path(__file__).resolve().parent.parent.parent.parent / "themes"
        )
    except Exception:
        pass
    if meipass:
        try:
            candidates.append(Path(meipass) / "themes")
        except Exception:
            pass
    # dedup preserve order
    return tuple(dict.fromkeys(candidates))


def _seed_examples(dest: Path) -> None:
    """Copy bundled README/.example files into a freshly created themes dir.

    Runs only for frozen builds and only while ``dest`` is still empty,
    so it never overwrites anything the user has already imported.

    Args:
        dest: Persistent user themes directory to seed.
    """
    src = _bundled_themes_dir()
    if src is None or not src.is_dir():
        return
    try:
        if any(dest.iterdir()):
            return
    except Exception:
        return
    for item in src.iterdir():
        name = item.name.lower()
        if name.startswith(_SEED_NAME_PREFIXES) or name.endswith(
            _SEED_NAME_SUFFIX
        ):
            try:
                shutil.copy2(item, dest / item.name)
            except Exception as e:
                _lg.debug(f"Could not seed {item.name} into {dest}: {e}")


def _theme_dir() -> Path | None:
    """Return a persistent, writable user themes directory, creating it
    on first use.

    Tries each candidate in ``_candidate_theme_dirs()`` order and keeps
    the first one that can actually be created/written to. Critically,
    when frozen this means ``exe.parent/themes`` is created (and seeded
    with the bundled README/.example files) instead of silently reusing
    the temporary ``_MEIPASS/themes`` extraction copy, which always
    "existed" and therefore always won under the old first-match logic
    -- so imports were written to a folder wiped on exit and
    ``exe.parent/themes`` was never created on disk.

    Falls back to a folder under the system temp directory if every
    candidate is unwritable (e.g. installed to a permission-locked
    path).

    Returns:
        Path to an existing, writable themes directory, or ``None`` if
        even the temp fallback fails.
    """
    for index, candidate in enumerate(_candidate_theme_dirs()):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            _lg.debug(f"Cannot use themes dir {candidate}: {e}")
            continue
        if index == 0:
            _seed_examples(candidate)
        return candidate

    fallback = Path(tempfile.gettempdir()) / "ywallhaven" / "themes"
    try:
        fallback.mkdir(parents=True, exist_ok=True)
        _lg.warning(f"All themes dir candidates failed; using {fallback}")
        return fallback
    except Exception as e:
        _lg.error(f"Cannot create fallback themes dir {fallback}: {e}")
        return None


def load_user_themes(force: bool = False) -> dict[str, ThemeDefinition]:
    """Scan themes dir for *.json and load valid ThemeDefinition.

    Args:
        force: Reload even if already cached.

    Returns:
        Dict of user themes by id.
    """
    global _USER_THEMES
    if _USER_THEMES and not force:
        return dict(_USER_THEMES)

    _USER_THEMES.clear()
    tdir = _theme_dir()
    _lg.info(
        f"Themes dir: {tdir}, exists={tdir is not None and tdir.is_dir()}."
    )
    if tdir is None or not tdir.is_dir():
        return {}

    for path in sorted(tdir.glob("*.json")):
        # skip example/README
        if path.name.lower().startswith("readme"):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            _lg.warning(f"Skipping theme {path.name}: invalid JSON ({e})")
            continue

        # allow both single object and {"themes": [...]}
        candidates = []
        if isinstance(raw, dict) and "themes" in raw:
            candidates = raw["themes"]
        elif isinstance(raw, list):
            candidates = raw
        else:
            candidates = [raw]

        for item in candidates:
            try:
                td = ThemeDefinition.model_validate(item)
                if td.is_builtin:
                    td = td.model_copy(update={"is_builtin": False})
                if td.id in _USER_THEMES:
                    _lg.warning(
                        f"Duplicate user theme id '{td.id}' in {path.name}, "
                        "overwriting previous."
                    )
                _USER_THEMES[td.id] = td
                _lg.debug(f"Loaded user theme '{td.id}' from {path.name}")
            except Exception as e:
                _lg.warning(
                    f"Skipping invalid theme in {path.name}: {e}"
                )
                continue

    return dict(_USER_THEMES)


def get_user_themes() -> dict[str, ThemeDefinition]:
    """Return cached user themes, loading if needed.

    Returns:
        Dict of user themes.
    """
    if not _USER_THEMES:
        return load_user_themes()
    return dict(_USER_THEMES)


def clear_cache() -> None:
    """Clear user theme cache (for tests)."""
    _USER_THEMES.clear()
