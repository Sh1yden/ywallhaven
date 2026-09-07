"""Regression tests for FilePicker service mounting (flet 0.86+).

In flet 0.86 ``FilePicker`` is a service that self-registers into
``page._services`` on construction. It must never be appended to
``page.overlay`` -- the client has no widget for it and renders
"unknown control: FilePicker". These tests guard the runtime
reference-pinning that keeps both pickers alive for the session.
"""

from dataclasses import dataclass, field
from typing import Any, List

import pytest

from app.interface.flet_app import _bind_file_pickers


@dataclass
class FakeServiceRegistry:
    """Minimal stand-in for flet's page-level service registry."""

    registered: List[Any] = field(default_factory=list)

    def register_service(self, service: Any) -> None:
        self.registered.append(service)


@dataclass
class FakePage:
    """Minimal stand-in exposing only the page surface used here."""

    _services: FakeServiceRegistry = field(default_factory=FakeServiceRegistry)
    overlay: List[Any] = field(default_factory=list)


@pytest.fixture
def fake_page(monkeypatch: pytest.MonkeyPatch) -> FakePage:
    """Pin the flet context page to a fake page during a test."""
    from flet.controls.context import _context_page

    page = FakePage()
    token = _context_page.set(page)
    try:
        yield page
    finally:
        _context_page.reset(token)


def test_bind_file_pickers_registers_services_without_overlay(fake_page):
    from flet import FilePicker

    file_picker, theme_picker = _bind_file_pickers(fake_page)

    assert isinstance(file_picker, FilePicker)
    assert isinstance(theme_picker, FilePicker)

    # Must be registered as services, not mounted into the page tree.
    assert fake_page.overlay == []
    assert set(fake_page._services.registered) == {file_picker, theme_picker}


def test_bind_file_pickers_pins_strong_references(fake_page):
    file_picker, theme_picker = _bind_file_pickers(fake_page)

    # The session GCs services by reference count after every event;
    # the page attributes are the guarantees the pickers stay alive.
    assert fake_page._ywallhaven_file_picker is file_picker
    assert fake_page._ywallhaven_theme_picker is theme_picker

    # Even after dropping the local names the pickers stay reachable.
    del file_picker, theme_picker
    assert isinstance(fake_page._ywallhaven_file_picker, object)
    assert isinstance(fake_page._ywallhaven_theme_picker, object)