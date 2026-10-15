"""Tests for the left panel filter collection (purity/categories)."""

import pytest


def _build_panel():
    from app.interface.components.left_panel import LeftPanel

    return LeftPanel()


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


class _BusPageStub:
    """Page stand-in with a recording pubsub client."""

    def __init__(self) -> None:
        self.sent: list = []
        self.subs: dict = {}
        self.unsubs: list = []
        self.pubsub = self

    def send_all_on_topic(self, topic, message):
        self.sent.append((topic, message))

    def subscribe_topic(self, topic, handler):
        self.subs[topic] = handler

    def unsubscribe_topic(self, topic):
        self.unsubs.append(topic)


def _attach_bus_page(monkeypatch, panel, stub):
    from app.interface.components.left_panel import LeftPanel

    monkeypatch.setattr(
        LeftPanel, "page", property(lambda self, _s=stub: _s)
    )


def test_apply_publishes_filters_on_bus(monkeypatch) -> None:
    from app.core.config import config
    from app.interface import bus as bus_mod

    try:
        panel = _build_panel()
    except Exception as exc:
        pytest.skip(f"Left panel requires a running Flet session: {exc}")

    stub = _BusPageStub()
    _attach_bus_page(monkeypatch, panel, stub)

    original = _with_config_api_key("test-key")
    try:
        panel._apply()
    finally:
        config.data.APIK = original

    assert len(stub.sent) == 1
    topic, payload = stub.sent[0]
    assert topic == bus_mod.TOPIC_FILTERS
    assert payload["api_key"] == "test-key"
    assert payload["filters"]["purity"] == "100"


def test_tag_message_searches_tag(monkeypatch) -> None:
    from app.core.config import config
    from app.interface import bus as bus_mod

    try:
        panel = _build_panel()
    except Exception as exc:
        pytest.skip(f"Left panel requires a running Flet session: {exc}")

    stub = _BusPageStub()
    _attach_bus_page(monkeypatch, panel, stub)
    monkeypatch.setattr(panel._search_field, "update", lambda *a, **k: None)

    original = _with_config_api_key("")
    try:
        panel._on_tag_message(bus_mod.TOPIC_TAG, {"name": "nature"})
    finally:
        config.data.APIK = original

    assert panel._search_field.value == "nature"
    assert stub.sent
    assert stub.sent[-1][0] == bus_mod.TOPIC_FILTERS

    panel._on_tag_message(bus_mod.TOPIC_TAG, {"name": ""})
    assert panel._search_field.value == "nature"


def test_bus_subscribe_unsubscribe_lifecycle(monkeypatch) -> None:
    from app.interface import bus as bus_mod

    try:
        panel = _build_panel()
    except Exception as exc:
        pytest.skip(f"Left panel requires a running Flet session: {exc}")

    stub = _BusPageStub()
    _attach_bus_page(monkeypatch, panel, stub)

    panel._subscribe_bus()
    assert bus_mod.TOPIC_TAG in stub.subs
    assert bus_mod.TOPIC_COLOR in stub.subs
    assert bus_mod.TOPIC_API_KEY in stub.subs

    panel._unsubscribe_bus()
    assert bus_mod.TOPIC_TAG in stub.unsubs
    assert bus_mod.TOPIC_COLOR in stub.unsubs
    assert bus_mod.TOPIC_API_KEY in stub.unsubs


def test_empty_query_relevance_falls_back_to_default() -> None:
    """Empty query never publishes relevance sorting."""
    from app.core.config import config

    try:
        panel = _build_panel()
    except Exception as exc:
        pytest.skip(f"Left panel requires a running Flet session: {exc}")

    original = _with_config_api_key("")
    try:
        panel._search_field.value = "   "
        panel._sorting_dd.value = "relevance"
        filters = panel._collect_filters()
    finally:
        config.data.APIK = original

    assert "query" not in filters
    assert filters["sorting"] == "date_added"


def test_nonempty_relevance_is_kept() -> None:
    """Non-empty query keeps relevance sorting untouched."""
    from app.core.config import config

    try:
        panel = _build_panel()
    except Exception as exc:
        pytest.skip(f"Left panel requires a running Flet session: {exc}")

    original = _with_config_api_key("")
    try:
        panel._search_field.value = "nature"
        panel._sorting_dd.value = "relevance"
        filters = panel._collect_filters()
    finally:
        config.data.APIK = original

    assert filters["query"] == "nature"
    assert filters["sorting"] == "relevance"


def test_apply_empty_relevance_publishes_default_feed(
    monkeypatch,
) -> None:
    """Apply with empty query syncs dropdown and publishes."""
    from app.core.config import config
    from app.interface import bus as bus_mod

    try:
        panel = _build_panel()
    except Exception as exc:
        pytest.skip(f"Left panel requires a running Flet session: {exc}")

    stub = _BusPageStub()
    _attach_bus_page(monkeypatch, panel, stub)
    monkeypatch.setattr(panel, "update", lambda *a, **k: None)
    monkeypatch.setattr(
        panel._search_field, "update", lambda *a, **k: None
    )

    original = _with_config_api_key("")
    try:
        panel._search_field.value = ""
        panel._search_field.error = "stale error"
        panel._sorting_dd.value = "relevance"
        panel._apply()
    finally:
        config.data.APIK = original

    assert panel._sorting_dd.value == "date_added"
    assert panel._search_field.error is None
    assert len(stub.sent) == 1
    topic, payload = stub.sent[0]
    assert topic == bus_mod.TOPIC_FILTERS
    assert payload["filters"]["sorting"] == "date_added"
    assert "query" not in payload["filters"]


def test_color_message_sets_dropdown_and_applies(monkeypatch) -> None:
    from app.core.config import config
    from app.interface import bus as bus_mod

    try:
        panel = _build_panel()
    except Exception as exc:
        pytest.skip(f"Left panel requires a running Flet session: {exc}")

    stub = _BusPageStub()
    _attach_bus_page(monkeypatch, panel, stub)
    monkeypatch.setattr(panel._colors_dd, "update", lambda *a, **k: None)

    original = _with_config_api_key("")
    try:
        panel._on_color_message(
            bus_mod.TOPIC_COLOR, {"color": "ff9900"}
        )
    finally:
        config.data.APIK = original

    assert panel._colors_dd.value == "ff9900"
    assert stub.sent
    topic, payload = stub.sent[-1]
    assert topic == bus_mod.TOPIC_FILTERS
    assert payload["filters"]["colors"] == "ff9900"


def test_color_message_ignores_invalid(monkeypatch) -> None:
    from app.interface import bus as bus_mod

    try:
        panel = _build_panel()
    except Exception as exc:
        pytest.skip(f"Left panel requires a running Flet session: {exc}")

    stub = _BusPageStub()
    _attach_bus_page(monkeypatch, panel, stub)
    before = panel._colors_dd.value

    panel._on_color_message(bus_mod.TOPIC_COLOR, {"color": "zzz"})
    panel._on_color_message(bus_mod.TOPIC_COLOR, {"color": ""})
    panel._on_color_message(bus_mod.TOPIC_COLOR, {})

    assert panel._colors_dd.value == before
    assert stub.sent == []


def test_custom_color_adds_dropdown_option(monkeypatch) -> None:
    from app.core.config import config

    try:
        panel = _build_panel()
    except Exception as exc:
        pytest.skip(f"Left panel requires a running Flet session: {exc}")

    monkeypatch.setattr(panel._colors_dd, "update", lambda *a, **k: None)
    monkeypatch.setattr(panel, "_apply", lambda: None)

    panel.search_color("5a4a3a")

    assert panel._colors_dd.value == "5a4a3a"
    assert "5a4a3a" in [opt.key for opt in panel._colors_dd.options]
    assert panel._collect_filters()["colors"] == "5a4a3a"

    panel.search_color("zzz")
    assert panel._colors_dd.value == "5a4a3a"


def test_api_key_message_applies_key(monkeypatch) -> None:
    from app.interface import bus as bus_mod

    try:
        panel = _build_panel()
    except Exception as exc:
        pytest.skip(f"Left panel requires a running Flet session: {exc}")

    stub = _BusPageStub()
    _attach_bus_page(monkeypatch, panel, stub)
    monkeypatch.setattr(panel, "_refresh_purity_state", lambda: None)
    monkeypatch.setattr(panel, "_apply", lambda: None)

    panel._on_api_key_message(
        bus_mod.TOPIC_API_KEY, {"api_key": "new-key"}
    )