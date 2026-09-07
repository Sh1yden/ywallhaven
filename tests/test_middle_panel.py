"""Tests for the middle panel pagination cache helpers."""

import asyncio

import pytest

from app.interface.components.middle_panel import MiddlePanel


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