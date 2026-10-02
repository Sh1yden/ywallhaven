"""Tests for the middle panel pagination cache helpers."""

import asyncio

import httpx
import pytest

from app.interface.components.middle_panel import MiddlePanel


def _http_error(status_code: int) -> httpx.HTTPStatusError:
    """Build an httpx error carrying a response with the given status."""
    request = httpx.Request("GET", "https://wallhaven.cc/api/v1/search")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError(
        f"Mock {status_code}", request=request, response=response
    )


def _error_without_response() -> httpx.HTTPError:
    """Timeout-like error with no attached response."""
    return httpx.ConnectTimeout("Mock timeout")


class _RecordingPageStub:
    """Stand-in for flet Page.run_task that records scheduled calls."""

    def __init__(self) -> None:
        self.scheduled: list = []

    def run_task(self, fn, *args, **kwargs):
        self.scheduled.append((fn, args, kwargs))
        return None


def _attach_page(monkeypatch, panel, stub) -> None:
    monkeypatch.setattr(
        MiddlePanel, "page", property(lambda self, _s=stub: _s)
    )


def _capture_middle_sleep(monkeypatch) -> list:
    """Replace asyncio.sleep with a recorder (no real waiting)."""
    delays: list = []

    async def _fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(
        "app.interface.components.middle_panel.asyncio.sleep", _fake_sleep
    )
    return delays


@pytest.fixture
def panel():
    """A detached MiddlePanel for pure-logic tests (no page attached)."""
    p = MiddlePanel()
    yield p
    asyncio.run(p.api_client.close())


def test_consume_prefetched_returns_matching_page(panel):
    panel._prefetched_page_number = 3
    panel._prefetched_page = [{"id": "w1"}]
    panel.state_page = 3

    assert panel._consume_prefetched() == [{"id": "w1"}]
    assert panel._prefetched_page is None
    assert panel._prefetched_page_number is None


def test_consume_prefetched_drops_stale_page(panel):
    panel._prefetched_page_number = 2
    panel._prefetched_page = [{"id": "w1"}]
    panel.state_page = 3

    assert panel._consume_prefetched() is None
    assert panel._prefetched_page is None
    assert panel._prefetched_page_number is None


def test_apply_filters_resets_pagination_state(panel, monkeypatch):
    class _PageStub:
        def run_task(self, fn, *args, **kwargs):
            self.scheduled = fn

    stub = _PageStub()
    monkeypatch.setattr(MiddlePanel, "page", property(lambda self: stub))

    panel._prefetched_page = [{"id": "w1"}]
    panel._prefetched_page_number = 1
    panel._load_wanted = True
    panel.state_page = 4
    panel._wallpapers = [{"id": "old"}]

    panel.apply_filters(api_key="k", filters={"q": "nature"})

    assert panel.state_page == 1
    assert panel.has_more is True
    assert panel._prefetched_page is None
    assert panel._prefetched_page_number is None
    assert panel._load_wanted is False
    assert panel._wallpapers == []
    assert stub.scheduled.__name__ == "load_more"


def test_load_tags_failure_logs_warning(caplog):
    """RightPanel._load_tags must swallow fetch errors with a warning."""
    import logging

    from app.interface.components.right_panel import RightPanel

    async def _boom(wallpaper_id: str):
        raise RuntimeError("boom-tags")

    caplog.set_level(logging.DEBUG, logger="ywallhaven")
    panel = RightPanel()
    panel._api_client.get_wallpaper = _boom

    async def _main():
        try:
            await panel._load_tags({"id": "abc123"})
        finally:
            await panel._api_client.close()

    asyncio.run(_main())  # must not raise

    assert any(
        r.levelname == "WARNING"
        and "Failed to fetch tags" in r.getMessage()
        for r in caplog.records
    )


def test_on_resize_failure_logs_debug(caplog):
    """_build_ui _on_resize must swallow broken page state with debug."""
    import logging

    from app.interface.flet_app import _build_ui

    class _WindowStub:
        icon = None

    class _PageStub:
        def __init__(self):
            self.title = None
            self.padding = None
            self.bgcolor = None
            self.window = _WindowStub()
            self.theme = None
            self.dark_theme = None
            self.theme_mode = None
            self.overlay = []
            self.width = 1200

        def add(self, *args, **kwargs):
            pass

        def run_task(self, fn, *args, **kwargs):
            pass

        def update(self):
            pass

    caplog.set_level(logging.DEBUG, logger="ywallhaven")
    page = _PageStub()
    asyncio.run(_build_ui(page))
    on_resize = page.on_resized
    assert callable(on_resize)

    page.width = object()  # non-comparable -> TypeError inside handler
    on_resize(None)  # must not raise

    assert any(
        r.levelname == "DEBUG"
        and "Resize handling failed" in r.getMessage()
        for r in caplog.records
    )


@pytest.mark.parametrize(
    "status,expected",
    [
        (429, True),
        (502, True),
        (503, True),
        (504, True),
        (500, False),
        (404, False),
    ],
)
def test_is_transient_error_matrix(status, expected):
    assert MiddlePanel._is_transient_error(_http_error(status)) is expected


def test_is_transient_error_without_response_is_false():
    # Factual behavior: MiddlePanel._is_transient_error returns False
    # when the error carries no response (unlike
    # WallhavenAPI._is_transient, which treats it as transient).
    assert MiddlePanel._is_transient_error(_error_without_response()) is False
    assert MiddlePanel._is_transient_error(httpx.HTTPError("boom")) is False


@pytest.mark.asyncio
async def test_load_more_transient_retries_bounded(panel, monkeypatch):
    stub = _RecordingPageStub()
    _attach_page(monkeypatch, panel, stub)
    monkeypatch.setattr(panel, "update", lambda *a, **k: None)
    _capture_middle_sleep(monkeypatch)

    async def _raise_transient(*args, **kwargs):
        raise _http_error(503)

    monkeypatch.setattr(panel.api_client, "search_wallpapers", _raise_transient)

    assert panel._transient_failures == 0
    assert panel.has_more is True
    assert panel.MAX_TRANSIENT_RETRIES == 3
    assert panel.RETRY_BASE_DELAY == 1.0

    for i, expected_delay in enumerate([1.0, 2.0, 4.0], start=1):
        await panel.load_more()
        assert panel._transient_failures == i
        assert panel.has_more is True
        assert len(stub.scheduled) == i
        fn, args, _kwargs = stub.scheduled[-1]
        assert getattr(fn, "__name__", "") == "_retry_with_delay"
        assert args[0] == pytest.approx(expected_delay)

    assert len(stub.scheduled) <= panel.MAX_TRANSIENT_RETRIES

    # Limit reached: fourth failure schedules no new retry, but one
    # slow poll while the grid is still empty after the outage.
    await panel.load_more()
    assert panel._transient_failures == 3
    assert panel.has_more is True
    fns = [getattr(fn, "__name__", "") for fn, _, _ in stub.scheduled]
    assert fns.count("_retry_with_delay") == 3
    assert fns.count("_poll_with_delay") == 1


@pytest.mark.asyncio
async def test_load_more_non_transient_no_retry(panel, monkeypatch):
    stub = _RecordingPageStub()
    _attach_page(monkeypatch, panel, stub)
    monkeypatch.setattr(panel, "update", lambda *a, **k: None)
    _capture_middle_sleep(monkeypatch)

    async def _raise_500(*args, **kwargs):
        raise _http_error(500)

    monkeypatch.setattr(panel.api_client, "search_wallpapers", _raise_500)

    await panel.load_more()

    assert panel._transient_failures == 0
    assert panel.has_more is True
    assert stub.scheduled == []
    assert panel.state_page == 1


@pytest.mark.asyncio
async def test_success_resets_counter(panel, monkeypatch):
    stub = _RecordingPageStub()
    _attach_page(monkeypatch, panel, stub)
    monkeypatch.setattr(panel, "update", lambda *a, **k: None)

    panel._transient_failures = 2

    async def _ok_empty(*args, **kwargs):
        return []

    monkeypatch.setattr(panel.api_client, "search_wallpapers", _ok_empty)

    await panel.load_more()

    assert panel._transient_failures == 0


@pytest.mark.asyncio
async def test_prefetch_failure_keeps_pagination(panel, monkeypatch):
    debug_msgs: list = []
    lg = panel._lg
    monkeypatch.setattr(
        lg, "debug", lambda msg, *a, **k: debug_msgs.append(str(msg))
    )

    async def _raise(*args, **kwargs):
        raise _http_error(503)

    monkeypatch.setattr(panel.api_client, "search_wallpapers", _raise)

    panel.has_more = True
    panel._prefetched_page = None
    panel._prefetched_page_number = None

    await panel._prefetch_next_page()

    assert panel._prefetched_page is None
    assert panel.has_more is True
    assert any("refetch" in m.lower() for m in debug_msgs)


class _OutagePageStub(_RecordingPageStub):
    """Page stand-in recording both tasks and dialogs."""

    def __init__(self) -> None:
        super().__init__()
        self.dialogs: list = []

    def show_dialog(self, dialog, *args, **kwargs):
        self.dialogs.append(dialog)
        return None


def _dialog_texts(stub) -> list:
    """Extract SnackBar message strings from recorded dialogs."""
    texts = []
    for dialog in stub.dialogs:
        content = getattr(dialog, "content", None)
        value = getattr(content, "value", "")
        texts.append(str(value))
    return texts


def _tile_text(panel) -> str:
    """Extract the outage placeholder message from the grid."""
    assert panel._outage_tile is not None
    column = panel._outage_tile.content
    return str(column.controls[1].value)


@pytest.mark.asyncio
async def test_outage_empty_grid_shows_tile_and_notifies_once(
    panel, monkeypatch
):
    """A dead Wallhaven (521) on an empty grid: tile + one snack + poll."""
    stub = _OutagePageStub()
    _attach_page(monkeypatch, panel, stub)
    monkeypatch.setattr(panel, "update", lambda *a, **k: None)
    _capture_middle_sleep(monkeypatch)

    async def _raise_521(*args, **kwargs):
        raise _http_error(521)

    monkeypatch.setattr(panel.api_client, "search_wallpapers", _raise_521)
    panel._transient_failures = panel.MAX_TRANSIENT_RETRIES

    await panel.load_more()

    assert panel._outage_tile is not None
    assert panel._outage_tile in panel.controls
    assert "down (HTTP 521)" in _tile_text(panel)
    assert len(stub.dialogs) == 1
    assert "down (HTTP 521)" in _dialog_texts(stub)[0]
    assert panel.has_more is True
    fns = [getattr(fn, "__name__", "") for fn, _, _ in stub.scheduled]
    assert "_poll_with_delay" in fns

    # Second failure: no second snack, tile kept, no duplicate poll.
    await panel.load_more()
    assert len(stub.dialogs) == 1
    assert panel._outage_tile in panel.controls
    fns2 = [getattr(fn, "__name__", "") for fn, _, _ in stub.scheduled]
    assert fns2.count("_poll_with_delay") == 1


@pytest.mark.asyncio
async def test_outage_loaded_grid_snacks_without_tile(panel, monkeypatch):
    """Outage with tiles on screen: snack only, grid untouched."""
    stub = _OutagePageStub()
    _attach_page(monkeypatch, panel, stub)
    monkeypatch.setattr(panel, "update", lambda *a, **k: None)

    panel._wallpapers = [{"id": "w1"}]
    before = list(panel.controls)
    panel._transient_failures = panel.MAX_TRANSIENT_RETRIES

    async def _raise_521(*args, **kwargs):
        raise _http_error(521)

    monkeypatch.setattr(panel.api_client, "search_wallpapers", _raise_521)

    await panel.load_more()

    assert panel._outage_tile is None
    assert panel.controls == before
    assert len(stub.dialogs) == 1
    assert "down (HTTP 521)" in _dialog_texts(stub)[0]


@pytest.mark.asyncio
async def test_outage_text_names_fault_side(panel, monkeypatch):
    """Site errors and app errors get different messages."""
    stub = _OutagePageStub()
    _attach_page(monkeypatch, panel, stub)
    monkeypatch.setattr(panel, "update", lambda *a, **k: None)

    async def _raise_500(*args, **kwargs):
        raise _http_error(500)

    monkeypatch.setattr(panel.api_client, "search_wallpapers", _raise_500)
    await panel.load_more()
    assert "returned an error (HTTP 500)" in _tile_text(panel)

    panel._hide_outage()
    panel.controls.clear()

    async def _raise_timeout(*args, **kwargs):
        raise _error_without_response()

    monkeypatch.setattr(
        panel.api_client, "search_wallpapers", _raise_timeout
    )
    await panel.load_more()
    assert _tile_text(panel).startswith("App error")


def test_retry_now_resets_and_reschedules(panel, monkeypatch):
    """Manual Retry clears the streak and reloads."""
    stub = _OutagePageStub()
    _attach_page(monkeypatch, panel, stub)

    panel._transient_failures = 3
    panel._outage_notified = True
    panel._poll_scheduled = True

    panel.retry_now()

    assert panel._transient_failures == 0
    assert panel._outage_notified is False
    assert panel._poll_scheduled is False
    fns = [getattr(fn, "__name__", "") for fn, _, _ in stub.scheduled]
    assert "load_more" in fns


@pytest.mark.asyncio
async def test_success_hides_outage_silently(panel, monkeypatch):
    """First good page removes the tile and resets notification."""
    stub = _OutagePageStub()
    _attach_page(monkeypatch, panel, stub)
    monkeypatch.setattr(panel, "update", lambda *a, **k: None)

    panel._outage_notified = True
    panel._outage_tile = "tile-stub"
    panel.controls.append("tile-stub")

    async def _ok(*args, **kwargs):
        return [
            {"id": "w1", "thumbs": {"small": "http://x/y.jpg"}},
        ]

    monkeypatch.setattr(panel.api_client, "search_wallpapers", _ok)

    await panel.load_more()

    assert panel._outage_tile is None
    assert "tile-stub" not in panel.controls
    assert panel._outage_notified is False
    assert len(panel._wallpapers) == 1


@pytest.mark.asyncio
async def test_poll_reloads_only_while_empty(panel, monkeypatch):
    """Slow poll reloads an empty grid and skips a filled one."""
    stub = _OutagePageStub()
    _attach_page(monkeypatch, panel, stub)
    monkeypatch.setattr(panel, "update", lambda *a, **k: None)
    _capture_middle_sleep(monkeypatch)

    calls: list = []

    async def _ok(*args, **kwargs):
        calls.append(1)
        return [{"id": "w1", "thumbs": {"small": "http://x/y.jpg"}}]

    monkeypatch.setattr(panel.api_client, "search_wallpapers", _ok)

    await panel._poll_with_delay(60.0)
    assert len(calls) == 1

    await panel._poll_with_delay(60.0)
    assert len(calls) == 1


class _BusPageStub(_RecordingPageStub):
    """Page stand-in with a recording pubsub client."""

    def __init__(self) -> None:
        super().__init__()
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


def _event(index: int):
    """Fake tap event carrying a tile index."""
    from types import SimpleNamespace

    return SimpleNamespace(control=SimpleNamespace(data=index))


def test_image_click_publishes_preview(panel, monkeypatch):
    from app.interface import bus as bus_mod

    stub = _BusPageStub()
    _attach_page(monkeypatch, panel, stub)
    wallpaper = {"id": "w1"}
    panel._wallpapers = [wallpaper]

    panel.handle_image_click(_event(0))

    assert stub.sent == [
        (bus_mod.TOPIC_PREVIEW, {"wallpaper": wallpaper, "index": 0})
    ]


def test_image_double_click_publishes_download_request(
    panel, monkeypatch
):
    from app.interface import bus as bus_mod

    stub = _BusPageStub()
    _attach_page(monkeypatch, panel, stub)
    wallpaper = {"id": "w1"}
    panel._wallpapers = [wallpaper]

    panel.handle_image_double_click(_event(0))

    assert stub.sent == [
        (bus_mod.TOPIC_DOWNLOAD_REQUEST, {"wallpaper": wallpaper})
    ]


def test_filters_message_reloads_gallery(panel, monkeypatch):
    from app.interface import bus as bus_mod

    stub = _BusPageStub()
    _attach_page(monkeypatch, panel, stub)
    monkeypatch.setattr(panel, "update", lambda *a, **k: None)
    panel._wallpapers = [{"id": "old"}]
    panel.state_page = 4

    async def _ok(*args, **kwargs):
        return []

    monkeypatch.setattr(panel.api_client, "search_wallpapers", _ok)

    panel._on_filters_message(
        bus_mod.TOPIC_FILTERS,
        {"api_key": "k", "filters": {"q": "nature"}},
    )

    assert panel.state_page == 1
    assert panel._wallpapers == []
    assert panel.api_client.apik == "k"


def test_bus_subscribe_unsubscribe_lifecycle(panel, monkeypatch):
    from app.interface import bus as bus_mod

    stub = _BusPageStub()
    _attach_page(monkeypatch, panel, stub)

    panel._subscribe_bus()
    assert bus_mod.TOPIC_FILTERS in stub.subs

    panel._unsubscribe_bus()
    assert bus_mod.TOPIC_FILTERS in stub.unsubs


def _gallery_page(page_no: int, count: int = 24) -> list:
    """Build a fake search page with distinct wallpaper ids."""
    return [
        {
            "id": f"p{page_no}-{i}",
            "thumbs": {"small": "http://x/s.jpg"},
        }
        for i in range(count)
    ]


@pytest.mark.asyncio
async def test_grid_window_evicts_oldest_pages(panel, monkeypatch):
    stub = _BusPageStub()
    _attach_page(monkeypatch, panel, stub)
    monkeypatch.setattr(panel, "update", lambda *a, **k: None)

    calls: list = []

    async def _paged(*args, **kwargs):
        calls.append(1)
        return _gallery_page(len(calls))

    monkeypatch.setattr(panel.api_client, "search_wallpapers", _paged)

    for _ in range(6):
        await panel.load_more()

    assert len(calls) == 6
    assert panel.state_page == 7
    assert panel.has_more is True
    assert len(panel._wallpapers) == panel.TILE_WINDOW
    assert len(panel.controls) == panel.TILE_WINDOW
    # Page 1 fell out of the window; page 2 is now first.
    assert panel._wallpapers[0]["id"] == "p2-0"
    assert panel._wallpapers[-1]["id"] == "p6-23"


@pytest.mark.asyncio
async def test_evicted_tiles_reindexed(panel, monkeypatch):
    from app.interface import bus as bus_mod

    stub = _BusPageStub()
    _attach_page(monkeypatch, panel, stub)
    monkeypatch.setattr(panel, "update", lambda *a, **k: None)

    calls: list = []

    async def _paged(*args, **kwargs):
        calls.append(1)
        return _gallery_page(len(calls))

    monkeypatch.setattr(panel.api_client, "search_wallpapers", _paged)

    for _ in range(6):
        await panel.load_more()

    datas = [tile.data for tile in panel.controls]
    assert datas == list(range(panel.TILE_WINDOW))

    # A click on the first visible tile resolves to page-2 wallpaper.
    panel.handle_image_click(_event(0))
    topic, payload = stub.sent[-1]
    assert topic == bus_mod.TOPIC_PREVIEW
    assert payload["wallpaper"]["id"] == "p2-0"
    assert payload["index"] == 0


@pytest.mark.asyncio
async def test_window_keeps_short_feeds_intact(panel, monkeypatch):
    _attach_page(monkeypatch, panel, _BusPageStub())
    monkeypatch.setattr(panel, "update", lambda *a, **k: None)

    async def _short(*args, **kwargs):
        return _gallery_page(1, count=10)

    monkeypatch.setattr(panel.api_client, "search_wallpapers", _short)

    await panel.load_more()

    assert len(panel._wallpapers) == 10
    assert [t.data for t in panel.controls] == list(range(10))