"""Tests for the collections grid and collection settings panels."""

import pytest

from app.interface import bus as bus_mod
from app.interface.components.collection_settings import (
    CollectionSettingsPanel,
)
from app.interface.components.collections_panel import (
    CollectionsPanel,
    resolve_cover,
    thumb_src,
)
from app.service.favorites import FAVORITES_ID, FavoritesStore


def _store(tmp_path):
    return FavoritesStore(tmp_path / "favorites.json")


def _wallpaper(wid="w1"):
    return {
        "id": wid,
        "path": f"https://example.com/{wid}.jpg",
        "thumbs": {"small": f"https://example.com/{wid}_s.jpg"},
    }


class _BusPageStub:
    def __init__(self) -> None:
        self.sent: list = []
        self.pubsub = self

    def send_all_on_topic(self, topic, message):
        self.sent.append((topic, message))

    def subscribe_topic(self, topic, handler):
        pass

    def unsubscribe_topic(self, topic):
        pass


def _attach(monkeypatch, panel, stub):
    monkeypatch.setattr(
        type(panel), "page", property(lambda self, _s=stub: _s)
    )


def test_thumb_src_prefers_small():
    assert thumb_src(_wallpaper()) == "https://example.com/w1_s.jpg"
    assert thumb_src({"path": "p"}) == "p"
    assert thumb_src({}) is None


def test_resolve_cover_modes():
    assert resolve_cover({"wallpapers": []})[0] == "heart"
    assert resolve_cover({"cover": {"mode": "icon"}}) == (
        "icon",
        "IMAGE",
    )
    assert resolve_cover(
        {"cover": {"mode": "icon", "icon": "FOLDER"}, "wallpapers": []}
    ) == ("icon", "FOLDER")
    kind, value = resolve_cover(
        {"cover": {"mode": "last"}, "wallpapers": [_wallpaper()]}
    )
    assert (kind, value) == ("image", "https://example.com/w1_s.jpg")
    assert resolve_cover(
        {
            "cover": {"mode": "wallpaper", "wallpaper_id": "zz"},
            "wallpapers": [_wallpaper()],
        }
    )[0] == "heart"


def test_grid_refresh_builds_tiles(tmp_path, monkeypatch):
    store = _store(tmp_path)
    store.create("Nature")
    photos = tmp_path / "photos"
    photos.mkdir()
    (photos / "a.jpg").write_bytes(b"a")
    store.add_folder(photos)

    panel = CollectionsPanel(store)

    kinds = [type(t).__name__ for t in panel._grid.controls]
    assert len(kinds) == 4  # favorites + nature + folder + create
    assert all(k == "GestureDetector" for k in kinds)


def test_tile_select_publishes(tmp_path, monkeypatch):
    store = _store(tmp_path)
    panel = CollectionsPanel(store)
    stub = _BusPageStub()
    _attach(monkeypatch, panel, stub)

    tile = panel._grid.controls[0]
    tile.on_tap(None)

    assert stub.sent == [
        (
            bus_mod.TOPIC_COLLECTION_SELECT,
            {"kind": "collection", "id": FAVORITES_ID},
        )
    ]


def test_create_tile_publishes_request(tmp_path, monkeypatch):
    store = _store(tmp_path)
    panel = CollectionsPanel(store)
    stub = _BusPageStub()
    _attach(monkeypatch, panel, stub)

    tile = panel._grid.controls[-1]
    tile.on_tap(None)

    assert stub.sent == [(bus_mod.TOPIC_COLLECTION_CREATE, {})]


def test_settings_rename_persists_and_notifies(tmp_path):
    store = _store(tmp_path)
    created = store.create("Old")
    notified: list = []
    panel = CollectionSettingsPanel(
        store, on_changed=lambda: notified.append(True)
    )
    panel.load_collection(store.get(created["id"]))

    name_field = None
    for control in panel.content.controls:
        if type(control).__name__ == "TextField" and control.label == "Name":
            name_field = control
    assert name_field is not None
    name_field.value = "New"
    name_field.on_submit(None)

    assert store.get(created["id"])["name"] == "New"
    assert notified


def test_settings_interval_validation(tmp_path):
    store = _store(tmp_path)
    panel = CollectionSettingsPanel(store, on_changed=lambda: None)
    panel.load_collection(store.get(FAVORITES_ID))

    interval = None
    for control in panel.content.controls:
        if (
            type(control).__name__ == "TextField"
            and control.label == "Interval, seconds"
        ):
            interval = control
    assert interval is not None
    interval.value = "5"
    interval.on_submit(None)
    assert interval.error == "Minimum 10 seconds"
    assert store.get(FAVORITES_ID)["settings"]["interval"] == 300
    interval.value = "60"
    interval.on_submit(None)
    assert store.get(FAVORITES_ID)["settings"]["interval"] == 60


def test_settings_switch_and_dropdowns(tmp_path):
    store = _store(tmp_path)
    panel = CollectionSettingsPanel(store, on_changed=lambda: None)
    panel.load_collection(store.get(FAVORITES_ID))

    switch = next(
        c for c in panel.content.controls if type(c).__name__ == "Switch"
    )
    switch.value = True
    switch.on_change(None)
    assert store.get(FAVORITES_ID)["settings"]["slideshow"] is True

    order = next(
        c
        for c in panel.content.controls
        if type(c).__name__ == "Dropdown" and c.label == "Order"
    )
    order.value = "random"
    order.on_select(None)
    assert store.get(FAVORITES_ID)["settings"]["order"] == "random"


def test_settings_folder_unlink(tmp_path):
    store = _store(tmp_path)
    photos = tmp_path / "photos"
    photos.mkdir()
    entry = store.add_folder(photos)
    notified: list = []
    panel = CollectionSettingsPanel(
        store, on_changed=lambda: notified.append(True)
    )
    panel.load_folder(entry, 0)
    assert panel._folder_id == entry["id"]

    panel._handle_unlink(None)

    assert store.folders() == []
    assert photos.is_dir()
    assert notified
