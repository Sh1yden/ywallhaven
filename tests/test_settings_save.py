"""Tests for SettingsPanel._on_save theme apply path."""

from types import SimpleNamespace

import pytest


def _make_panel(monkeypatch, page, theme_value="ocean"):
    from app.interface.components import settings as settings_mod

    panel = settings_mod.SettingsPanel.__new__(
        settings_mod.SettingsPanel
    )
    monkeypatch.setattr(
        settings_mod.SettingsPanel,
        "page",
        property(lambda self, _p=page: _p),
    )
    panel._theme_dd = SimpleNamespace(value=theme_value)
    panel._api_key_field = SimpleNamespace(value="")
    panel._port_field = SimpleNamespace(
        value="9999", error=None, update=lambda *a, **k: None
    )
    panel._mode_dd = SimpleNamespace(value="dev")
    panel._log_lvl_dd = SimpleNamespace(value="INFO")
    panel._check_updates_sw = SimpleNamespace(value=True)
    panel._prereleases_sw = SimpleNamespace(value=False)
    monkeypatch.setattr(
        panel, "_show_saved_notice", lambda: page.dialogs.append("saved")
    )
    return panel


def _make_page():
    chip = SimpleNamespace(value="Old", updated=False)
    chip.update = lambda *a, **k: setattr(chip, "updated", True)
    page = SimpleNamespace(
        dialogs=[], updated=False, _ywallhaven_theme_label=chip
    )
    page.update = lambda *a, **k: setattr(page, "updated", True)
    page.show_dialog = lambda dlg: page.dialogs.append(dlg)
    return page


def test_on_save_applies_theme_and_updates_chip(monkeypatch):
    from app.core.config import config
    from app.interface.components import settings as settings_mod

    page = _make_page()
    panel = _make_panel(monkeypatch, page, theme_value="ocean")

    old_theme = config.data.THEME
    config.data.THEME = "dark_default"
    monkeypatch.setattr(config, "update", lambda **kw: None)
    monkeypatch.setattr(
        settings_mod.bus, "publish", lambda *a, **k: True
    )

    try:
        panel._on_save(SimpleNamespace())
    finally:
        config.data.THEME = old_theme

    assert page.updated is True
    assert page._ywallhaven_theme_label.value == "Ocean"
    assert page.dialogs == ["saved"]


def test_on_save_theme_failure_shows_error(monkeypatch):
    import app.interface.components.settings as settings_mod
    import app.interface.themes as themes_mod
    from app.core.config import config

    page = _make_page()
    panel = _make_panel(monkeypatch, page, theme_value="ocean")

    old_theme = config.data.THEME
    config.data.THEME = "dark_default"
    monkeypatch.setattr(config, "update", lambda **kw: None)

    def _boom(p, tid):
        raise RuntimeError("boom-theme")

    monkeypatch.setattr(themes_mod, "apply_theme", _boom)

    try:
        panel._on_save(SimpleNamespace())
    finally:
        config.data.THEME = old_theme

    assert "saved" not in page.dialogs
    assert len(page.dialogs) == 1
