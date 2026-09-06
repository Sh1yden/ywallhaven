"""Tests for theme registry, schema and loader."""

import json
from pathlib import Path

import pytest

from app.interface.themes.builtin import BUILTIN_THEMES
from app.interface.themes.loader import clear_cache, get_user_themes, load_user_themes
from app.interface.themes.schema import ThemeDefinition


def test_builtin_themes_valid() -> None:
    """All builtin themes must validate and produce Flet Theme."""
    assert len(BUILTIN_THEMES) == 9
    assert "kanagawa_wave" in BUILTIN_THEMES
    assert "kanagawa_lotus" in BUILTIN_THEMES
    for tid, td in BUILTIN_THEMES.items():
        assert td.id == tid
        # validate via pydantic
        ThemeDefinition.model_validate(td.model_dump())
        # to_flet_theme must not raise
        theme = td.to_flet_theme()
        assert theme is not None
        assert theme.use_material3 is True


def test_kanagawa_wave_dark_lotus_light() -> None:
    """Kanagawa themes modes must match wave=dark, lotus=light."""
    assert BUILTIN_THEMES["kanagawa_wave"].mode == "dark"
    assert BUILTIN_THEMES["kanagawa_lotus"].mode == "light"
    # seed must be normalized
    assert BUILTIN_THEMES["kanagawa_wave"].seed == "#7E9CD8"
    assert BUILTIN_THEMES["kanagawa_lotus"].seed == "#4D699B"


def test_schema_hex_normalization() -> None:
    """3-digit hex expands, seed normalized."""
    td = ThemeDefinition(
        id="test_hex", name="Test", mode="dark", seed="#abc"
    )
    assert td.seed == "#AABBCC"
    td2 = ThemeDefinition(
        id="test_hex2",
        name="Test2",
        mode="light",
        seed="#aabbcc",
        colors={"primary": "#fff", "surface": "#123456"},
    )
    assert td2.colors["primary"] == "#FFFFFF"


def test_schema_invalid_hex() -> None:
    """Invalid hex should raise."""
    with pytest.raises(Exception):
        ThemeDefinition(
            id="bad_hex", name="Bad", mode="dark", seed="nothex"
        )
    with pytest.raises(Exception):
        ThemeDefinition(
            id="bad_hex2",
            name="Bad2",
            mode="dark",
            seed="#GGGGGG",
        )


def test_schema_invalid_id() -> None:
    """Bad id must raise."""
    with pytest.raises(Exception):
        ThemeDefinition(
            id="Bad-ID!", name="Bad", mode="dark", seed="#000000"
        )
    with pytest.raises(Exception):
        ThemeDefinition(id="ab", name="Ab", mode="dark", seed="#000000")


def test_schema_unknown_color_key() -> None:
    """Unknown color key must raise."""
    with pytest.raises(Exception, match="unknown color key"):
        ThemeDefinition(
            id="bad_color",
            name="Bad",
            mode="dark",
            seed="#000000",
            colors={"unknown_key": "#FFFFFF"},
        )


def test_schema_bad_color_hex() -> None:
    """Bad color hex must raise."""
    with pytest.raises(Exception):
        ThemeDefinition(
            id="bad_chex",
            name="Bad",
            mode="dark",
            seed="#000000",
            colors={"primary": "zzzzzz"},
        )


def test_to_flet_theme_seed_only() -> None:
    """Seed-only theme uses color_scheme_seed."""
    td = ThemeDefinition(
        id="seed_only", name="Seed", mode="dark", seed="#6750A4"
    )
    theme = td.to_flet_theme()
    assert theme.color_scheme_seed == "#6750A4"
    assert theme.color_scheme is None


def test_to_flet_theme_hybrid() -> None:
    """Hybrid theme creates ColorScheme with overrides."""
    td = ThemeDefinition(
        id="hybrid_test",
        name="Hybrid",
        mode="dark",
        seed="#7E9CD8",
        colors={"primary": "#FFFFFF", "surface": "#101418"},
    )
    theme = td.to_flet_theme()
    assert theme.color_scheme is not None
    assert theme.color_scheme.primary == "#FFFFFF"
    assert theme.color_scheme.surface == "#101418"


def test_hybrid_auto_primary() -> None:
    """Hybrid without primary should inject seed as primary."""
    td = ThemeDefinition(
        id="hybrid_auto",
        name="Hybrid Auto",
        mode="dark",
        seed="#123456",
        colors={"surface": "#000000"},
    )
    theme = td.to_flet_theme()
    assert theme.color_scheme.primary == "#123456"


def test_loader_ignores_invalid_json(tmp_path, monkeypatch) -> None:
    """Loader must skip invalid JSON and bad theme files."""
    monkeypatch.chdir(tmp_path)
    clear_cache()
    tdir = tmp_path / "themes"
    tdir.mkdir()
    (tdir / "bad.json").write_text("{not json", encoding="utf-8")
    (tdir / "bad2.json").write_text(
        json.dumps({"id": "bad", "name": "Bad", "mode": "dark", "seed": "zzz"}),
        encoding="utf-8",
    )
    (tdir / "good.json").write_text(
        json.dumps(
            {"id": "good_theme", "name": "Good", "mode": "dark", "seed": "#123456"}
        ),
        encoding="utf-8",
    )
    user = load_user_themes(force=True)
    assert "good_theme" in user
    assert "bad" not in user
    clear_cache()


def test_loader_duplicate_id_overwrites(tmp_path, monkeypatch) -> None:
    """Duplicate id should last write wins."""
    monkeypatch.chdir(tmp_path)
    clear_cache()
    tdir = tmp_path / "themes"
    tdir.mkdir()
    (tdir / "a.json").write_text(
        json.dumps(
            {"id": "dup", "name": "First", "mode": "dark", "seed": "#111111"}
        ),
        encoding="utf-8",
    )
    (tdir / "b.json").write_text(
        json.dumps(
            {"id": "dup", "name": "Second", "mode": "light", "seed": "#222222"}
        ),
        encoding="utf-8",
    )
    user = load_user_themes(force=True)
    assert user["dup"].name == "Second"
    clear_cache()


def test_registry_list_and_legacy(tmp_path, monkeypatch) -> None:
    """Registry must merge builtin+user and support legacy dark/light."""
    monkeypatch.chdir(tmp_path)
    clear_cache()
    from app.interface.themes import get_theme, list_themes

    all_themes = list_themes()
    assert len(all_themes) >= 9
    # legacy
    assert get_theme("dark").id == "dark_default"
    assert get_theme("light").id == "light_default"
    assert get_theme("nonexistent") is None
    clear_cache()


def test_apply_theme_sets_mode(monkeypatch) -> None:
    """apply_theme must set theme_mode correctly."""
    from types import SimpleNamespace

    from app.interface.themes import apply_theme

    # mock page
    page = SimpleNamespace(theme=None, dark_theme=None, theme_mode=None)

    # patch update to no-op
    page.update = lambda: None
    # need _Control__uid attr to avoid update attempt
    page._Control__uid = None

    td = apply_theme(page, "kanagawa_wave")
    assert td.id == "kanagawa_wave"
    # check theme_mode set (enum value contains DARK)
    assert "DARK" in str(page.theme_mode) or "dark" in str(page.theme_mode).lower()

    td2 = apply_theme(page, "kanagawa_lotus")
    assert td2.id == "kanagawa_lotus"
    assert "LIGHT" in str(page.theme_mode) or "light" in str(page.theme_mode).lower()

    # fallback for unknown
    td3 = apply_theme(page, "unknown_xyz")
    assert td3.id == "dark_default"
