"""Tests for the fullscreen zoom controls of the right panel."""

import asyncio
from types import SimpleNamespace

import pytest

from app.interface.components.right_panel import RightPanel


@pytest.fixture
def panel():
    """A detached RightPanel with a built fullscreen layer."""
    p = RightPanel()
    p._build_fullscreen_layer()
    # Detached controls cannot push updates; swallow them.
    p._zoom_box.update = lambda *a, **k: None
    p._fullscreen_layer.update = lambda *a, **k: None
    yield p
    asyncio.run(p._api_client.close())


def _wheel(dy: float):
    """Fake a mouse-wheel event with the given vertical delta."""
    return SimpleNamespace(scroll_delta=SimpleNamespace(x=0, y=dy))


def test_zoom_buttons_clamp_to_range(panel):
    for _ in range(20):
        panel.zoom_in()
    assert panel._zoom == panel.ZOOM_MAX
    assert panel._zoom_box.scale == panel.ZOOM_MAX

    for _ in range(20):
        panel.zoom_out()
    assert panel._zoom == panel.ZOOM_MIN
    assert panel._zoom_box.scale == panel.ZOOM_MIN


def test_zoom_reset_restores_default(panel):
    panel.zoom_in()
    panel.zoom_in()
    assert panel._zoom > panel.ZOOM_MIN

    panel.zoom_reset()
    assert panel._zoom == panel.ZOOM_MIN
    assert panel._zoom_box.scale == panel.ZOOM_MIN
    assert panel._pinch_base is None


def test_wheel_up_zooms_in_down_zooms_out(panel):
    panel._on_zoom_scroll(_wheel(-1.0))
    assert panel._zoom == pytest.approx(
        panel.ZOOM_MIN + panel.ZOOM_WHEEL_STEP
    )

    panel._on_zoom_scroll(_wheel(2.0))
    assert panel._zoom == panel.ZOOM_MIN

    before = panel._zoom
    panel._on_zoom_scroll(_wheel(0.0))
    assert panel._zoom == before


def test_pinch_scales_relative_to_gesture_start(panel):
    panel._zoom = 2.0
    panel._on_pinch_start(SimpleNamespace())
    assert panel._pinch_base == 2.0

    panel._on_pinch_update(SimpleNamespace(scale=1.5))
    assert panel._zoom == pytest.approx(3.0)

    panel._on_pinch_update(SimpleNamespace(scale=10.0))
    assert panel._zoom == panel.ZOOM_MAX


def test_fullscreen_tap_ignored_while_zoomed(panel):
    closed: list = []
    panel.close_fullscreen = lambda e: closed.append(e)

    panel._zoom = 2.0
    panel._on_fullscreen_tap(SimpleNamespace())
    assert closed == []

    panel._zoom = panel.ZOOM_MIN
    panel._on_fullscreen_tap(SimpleNamespace())
    assert len(closed) == 1


def test_close_fullscreen_resets_zoom(panel):
    panel._zoom = 3.0
    panel._fullscreen_image.src = "http://x/w.jpg"
    panel._backdrop_image.src = "http://x/w.jpg"
    panel._fullscreen_layer.visible = True

    panel.close_fullscreen(SimpleNamespace())

    assert panel._zoom == panel.ZOOM_MIN
    assert panel._zoom_box.scale == panel.ZOOM_MIN
    assert panel._fullscreen_image.src == ""
    assert panel._backdrop_image.src == ""
    assert panel._fullscreen_layer.visible is False


def test_refresh_resets_zoom_on_navigation(panel):
    panel._last_wallpaper = {"id": "w1", "path": "http://x/w.jpg"}
    panel._zoom = 2.5

    panel._refresh_fullscreen_image()

    assert panel._zoom == panel.ZOOM_MIN
    assert panel._fullscreen_image.src == "http://x/w.jpg"
    assert panel._backdrop_image.src == "http://x/w.jpg"


class _BusPageStub:
    """Page stand-in with a recording pubsub client."""

    def __init__(self) -> None:
        self.sent: list = []
        self.subs: dict = {}
        self.unsubs: list = []
        self.pubsub = self
        self.tasks: list = []
        self.dialogs: list = []

    def send_all_on_topic(self, topic, message):
        self.sent.append((topic, message))

    def subscribe_topic(self, topic, handler):
        self.subs[topic] = handler

    def unsubscribe_topic(self, topic):
        self.unsubs.append(topic)

    def run_task(self, fn, *args, **kwargs):
        self.tasks.append((fn, args, kwargs))

    def show_dialog(self, dialog, *args, **kwargs):
        self.dialogs.append(dialog)

    def pop_dialog(self, *args, **kwargs):
        self.dialogs.append("popped")


def _attach_bus_page(monkeypatch, panel, stub):
    monkeypatch.setattr(
        RightPanel, "page", property(lambda self, _s=stub: _s)
    )


def test_open_tag_publishes_tag(panel, monkeypatch):
    from app.interface import bus as bus_mod

    stub = _BusPageStub()
    _attach_bus_page(monkeypatch, panel, stub)

    panel._open_tag("nature")
    panel._open_tag("")

    assert stub.sent == [(bus_mod.TOPIC_TAG, {"name": "nature"})]


def test_wallpaper_click_publishes_request(panel, monkeypatch):
    from app.interface import bus as bus_mod

    stub = _BusPageStub()
    _attach_bus_page(monkeypatch, panel, stub)
    panel._last_wallpaper = {"id": "w1", "path": "http://x/w.jpg"}

    panel._handle_wallpaper_click(SimpleNamespace())

    assert stub.sent == [
        (bus_mod.TOPIC_SET_WALLPAPER, {"url": "http://x/w.jpg"})
    ]


def test_wallpaper_click_ignores_missing_url(panel, monkeypatch):
    stub = _BusPageStub()
    _attach_bus_page(monkeypatch, panel, stub)
    panel._last_wallpaper = {"id": "w1"}

    panel._handle_wallpaper_click(SimpleNamespace())

    assert stub.sent == []


def test_preview_message_renders_preview(panel, monkeypatch):
    from app.interface import bus as bus_mod

    stub = _BusPageStub()
    _attach_bus_page(monkeypatch, panel, stub)
    monkeypatch.setattr(panel, "update", lambda *a, **k: None)
    wallpaper = {
        "id": "w1",
        "path": "http://x/w.jpg",
        "thumbs": {"small": "http://x/s.jpg"},
    }

    panel._on_preview_message(
        bus_mod.TOPIC_PREVIEW, {"wallpaper": wallpaper, "index": 3}
    )

    assert panel._last_wallpaper is wallpaper
    assert panel._current_index == 3

    panel._on_preview_message(bus_mod.TOPIC_PREVIEW, {"wallpaper": None})
    assert panel._last_wallpaper is wallpaper


def test_download_request_opens_dialog(panel, monkeypatch):
    from app.interface import bus as bus_mod

    stub = _BusPageStub()
    _attach_bus_page(monkeypatch, panel, stub)
    wallpaper = {
        "id": "w1",
        "path": "http://x/w.jpg",
        "dimension_x": 1920,
        "dimension_y": 1080,
        "file_type": "image/jpeg",
    }

    panel._on_download_request(
        bus_mod.TOPIC_DOWNLOAD_REQUEST, {"wallpaper": wallpaper}
    )

    assert panel._last_wallpaper is wallpaper
    shown = [
        d for d in stub.dialogs if not isinstance(d, str)
    ]
    assert len(shown) == 1


def test_resolution_choose_publishes_download(panel, monkeypatch):
    from app.interface import bus as bus_mod

    stub = _BusPageStub()
    _attach_bus_page(monkeypatch, panel, stub)
    panel._last_wallpaper = {"id": "w1", "path": "http://x/w.jpg"}
    monkeypatch.setattr(panel, "_close_dialog", lambda e: None)

    option = panel._resolution_option("1920x1080", (1920, 1080), "w1", ".jpg")
    option.on_click(SimpleNamespace())

    assert stub.sent == [
        (
            bus_mod.TOPIC_DOWNLOAD,
            {
                "url": "http://x/w.jpg",
                "file_name": "w1-1920x1080.jpg",
                "size": (1920, 1080),
            },
        )
    ]


def test_bus_subscribe_unsubscribe_lifecycle(panel, monkeypatch):
    from app.interface import bus as bus_mod

    stub = _BusPageStub()
    _attach_bus_page(monkeypatch, panel, stub)

    panel._subscribe_bus()
    assert bus_mod.TOPIC_PREVIEW in stub.subs
    assert bus_mod.TOPIC_DOWNLOAD_REQUEST in stub.subs
    assert bus_mod.TOPIC_API_KEY in stub.subs

    panel._unsubscribe_bus()
    assert bus_mod.TOPIC_PREVIEW in stub.unsubs
    assert bus_mod.TOPIC_DOWNLOAD_REQUEST in stub.unsubs
    assert bus_mod.TOPIC_API_KEY in stub.unsubs


def test_api_key_message_updates_client(panel):
    panel._on_api_key_message("ywallhaven/api_key", {"api_key": "k"})
    assert panel._api_client.apik == "k"
