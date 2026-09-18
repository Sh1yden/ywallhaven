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
    p = MiddlePanel(right_panel=None)
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

    caplog.set_level(logging.DEBUG)
    panel = RightPanel(on_download=lambda *args, **kwargs: None)
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

    # Limit reached: fourth failure schedules nothing new.
    await panel.load_more()
    assert panel._transient_failures == 3
    assert panel.has_more is True
    assert len(stub.scheduled) == 3


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