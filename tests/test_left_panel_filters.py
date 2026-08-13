"""Tests for the left panel filter collection (purity/categories)."""

import pytest


def _build_panel():
    from app.interface.components.left_panel import LeftPanel

    return LeftPanel(middle_panel=object())


def _with_config_api_key(value: str):
    from app.core.config import config

    original = config.data.APIK
    config.data.APIK = value
    return original


def test_purity_forced_to_sfw_without_api_key() -> None:
    from app.core.config import config

    try:
        panel = _build_panel()
    except Exception as exc:
        pytest.skip(f"Left panel requires a running Flet session: {exc}")

    original = _with_config_api_key("")
    try:
        filters = panel._collect_filters()
    finally:
        config.data.APIK = original

    assert filters["purity"] == "100"


def test_purity_follows_checkboxes_with_api_key() -> None:
    from app.core.config import config

    try:
        panel = _build_panel()
    except Exception as exc:
        pytest.skip(f"Left panel requires a running Flet session: {exc}")

    original = _with_config_api_key("test-key")
    try:
        panel._sketchy_cb.value = True
        filters = panel._collect_filters()
    finally:
        config.data.APIK = original

    assert filters["purity"] == "110"


def test_categories_dropped_when_all_disabled() -> None:
    from app.core.config import config

    try:
        panel = _build_panel()
    except Exception as exc:
        pytest.skip(f"Left panel requires a running Flet session: {exc}")

    original = _with_config_api_key("test-key")
    try:
        panel._general_cb.value = False
        panel._anime_cb.value = False
        panel._people_cb.value = False
        filters = panel._collect_filters()
    finally:
        config.data.APIK = original

    assert "categories" not in filters