"""Loader for user-defined themes from ./themes/*.json."""

import json
import sys
from pathlib import Path

from app.core import get_logger
from app.interface.themes.schema import ThemeDefinition

_lg = get_logger()

_USER_THEMES: dict[str, ThemeDefinition] = {}


def _candidate_theme_dirs() -> tuple[Path, ...]:
    """Return possible directories where user themes may live.

    Order: cwd first (for tests/tmp), then repo root, then MEIPASS,
    then exe parent. This ensures tmp_path wins in tests.

    Returns:
        Tuple of candidate paths, deduplicated.
    """
    candidates: list[Path] = []
    # cwd first
    try:
        candidates.append(Path.cwd() / "themes")
    except Exception:
        pass
    # repo root
    try:
        candidates.append(
            Path(__file__).resolve().parent.parent.parent.parent / "themes"
        )
    except Exception:
        pass
    # MEIPASS
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        try:
            candidates.append(Path(meipass) / "themes")
        except Exception:
            pass
    # exe parent
    try:
        exe_parent = Path(sys.executable).parent
        candidates.append(exe_parent / "themes")
    except Exception:
        pass
    # dedup preserve order
    return tuple(dict.fromkeys(candidates))


def _theme_dir() -> Path | None:
    """Return the first existing themes dir, or create cwd/themes.

    Returns:
        Path to themes directory.
    """
    for d in _candidate_theme_dirs():
        if d.is_dir():
            return d
    # create in cwd if none exists
    fallback = Path.cwd() / "themes"
    try:
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback
    except Exception as e:
        _lg.warning(f"Cannot create themes dir {fallback}: {e}")
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
