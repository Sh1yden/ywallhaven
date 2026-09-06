"""Theme registry: builtin + user themes, apply helper."""

from typing import Literal

from app.core import get_logger
from app.interface.themes.builtin import BUILTIN_THEMES
from app.interface.themes.loader import (
    get_user_themes,
    load_user_themes,
)
from app.interface.themes.schema import ThemeDefinition

_lg = get_logger()

__all__ = [
    "ThemeDefinition",
    "BUILTIN_THEMES",
    "list_themes",
    "get_theme",
    "apply_theme",
    "reload_user_themes",
]


def list_themes() -> dict[str, ThemeDefinition]:
    """Return all themes (builtin + user, user wins on conflict).

    Returns:
        Dict id -> ThemeDefinition.
    """
    user = get_user_themes()
    merged: dict[str, ThemeDefinition] = dict(BUILTIN_THEMES)
    merged.update(user)
    return merged


def get_theme(theme_id: str) -> ThemeDefinition | None:
    """Get theme by id.

    Args:
        theme_id: Theme identifier.

    Returns:
        ThemeDefinition or None.
    """
    # Builtin direct
    if theme_id in BUILTIN_THEMES:
        # user may override builtin id
        user = get_user_themes()
        return user.get(theme_id, BUILTIN_THEMES[theme_id])
    # Check user
    user = get_user_themes()
    if theme_id in user:
        return user[theme_id]
    # legacy alias dark/light
    legacy = {"dark": "dark_default", "light": "light_default"}
    if theme_id in legacy:
        return get_theme(legacy[theme_id])
    return None


def reload_user_themes() -> dict[str, ThemeDefinition]:
    """Force reload user themes from disk.

    Returns:
        Updated user themes dict.
    """
    load_user_themes(force=True)
    return list_themes()


def apply_theme(page, theme_id: str) -> ThemeDefinition:
    """Apply theme to Flet Page.

    Args:
        page: Flet Page.
        theme_id: Theme identifier.

    Returns:
        Applied ThemeDefinition.
    """
    from flet import ThemeMode

    td = get_theme(theme_id)
    if td is None:
        _lg.warning(f"Theme '{theme_id}' not found, fallback to dark_default")
        td = BUILTIN_THEMES["dark_default"]

    flet_theme = td.to_flet_theme()

    # Apply to both theme and dark_theme for consistency
    try:
        page.theme = flet_theme
        page.dark_theme = flet_theme
    except Exception:
        page.theme = flet_theme

    page.theme_mode = (
        ThemeMode.DARK if td.mode == "dark" else ThemeMode.LIGHT
    )

    # Try update if page is already mounted
    try:
        if getattr(page, "_Control__uid", None) is not None:
            page.update()
    except Exception:
        pass

    _lg.debug(f"Applied theme '{td.id}' mode={td.mode}")
    return td
