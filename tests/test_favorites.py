"""Tests for the local favorites store (isolated files)."""

from app.service.favorites import (
    FAVORITES_ID,
    FavoritesStore,
    local_id,
)


def _store(tmp_path):
    return FavoritesStore(tmp_path / "favorites.json")


def _wallpaper(wid="w1", path="https://example.com/w1.jpg"):
    return {
        "id": wid,
        "path": path,
        "thumbs": {"small": path},
        "resolution": "1920x1080",
    }


def test_creates_default_with_favorites(tmp_path):
    store = _store(tmp_path)

    collections = store.collections()

    assert len(collections) == 1
    assert collections[0]["id"] == FAVORITES_ID
    assert collections[0]["wallpapers"] == []
    assert (tmp_path / "favorites.json").is_file()


def test_corrupted_file_recreated(tmp_path):
    target = tmp_path / "favorites.json"
    target.write_text("{broken", encoding="utf-8")

    store = FavoritesStore(target)

    assert [c["id"] for c in store.collections()] == [FAVORITES_ID]


def test_add_and_duplicate(tmp_path):
    store = _store(tmp_path)

    assert store.add(FAVORITES_ID, _wallpaper()) is True
    assert store.add(FAVORITES_ID, _wallpaper()) is False
    assert store.contains(FAVORITES_ID, "w1") is True

    assert store.remove(FAVORITES_ID, "w1") is True
    assert store.remove(FAVORITES_ID, "w1") is False
    assert store.contains(FAVORITES_ID, "w1") is False


def test_add_unknown_collection(tmp_path):
    store = _store(tmp_path)

    assert store.add("nope", _wallpaper()) is False


def test_create_rename_delete(tmp_path):
    store = _store(tmp_path)

    assert store.create("  ") is None
    created = store.create("Nature")
    assert created is not None
    assert created["settings"]["interval"] == 300

    assert store.rename(created["id"], "  ") is False
    assert store.rename(created["id"], "Mountains") is True
    assert store.get(created["id"])["name"] == "Mountains"

    assert store.delete(FAVORITES_ID) is False
    assert store.delete("nope") is False
    assert store.delete(created["id"]) is True
    assert store.get(created["id"]) is None


def test_clear_keeps_collection(tmp_path):
    store = _store(tmp_path)
    store.add(FAVORITES_ID, _wallpaper())

    assert store.clear(FAVORITES_ID) is True
    assert store.get(FAVORITES_ID)["wallpapers"] == []
    assert store.clear("nope") is False


def test_cover_and_settings(tmp_path):
    store = _store(tmp_path)

    assert store.set_cover(FAVORITES_ID, {"mode": "icon"}) is True
    assert store.get(FAVORITES_ID)["cover"] == {"mode": "icon"}
    assert store.set_cover("nope", {}) is False

    assert store.update_settings(FAVORITES_ID, interval=60) is True
    assert store.get(FAVORITES_ID)["settings"]["interval"] == 60
    assert store.update_settings(FAVORITES_ID, bogus=1) is True
    assert "bogus" not in store.get(FAVORITES_ID)["settings"]


def test_persists_across_instances(tmp_path):
    store = _store(tmp_path)
    store.add(FAVORITES_ID, _wallpaper())
    store.create("Second")

    again = FavoritesStore(tmp_path / "favorites.json")

    assert again.contains(FAVORITES_ID, "w1") is True
    assert len(again.collections()) == 2


def test_add_folder_and_scan(tmp_path):
    photos = tmp_path / "photos"
    photos.mkdir()
    (photos / "a.jpg").write_bytes(b"a")
    (photos / "b.png").write_bytes(b"b")
    (photos / "notes.txt").write_bytes(b"x")
    sub = photos / "sub"
    sub.mkdir()
    (sub / "c.jpg").write_bytes(b"c")

    store = _store(tmp_path)
    assert store.add_folder(tmp_path / "missing") is None
    entry = store.add_folder(photos)
    assert entry is not None
    assert store.add_folder(photos) is None  # duplicate
    assert len(store.folders()) == 1

    found = FavoritesStore.scan_folder(photos)
    assert sorted(w["id"] for w in found) == sorted(
        [local_id(photos / "a.jpg"), local_id(photos / "b.png")]
    )
    assert all(w["thumbs"]["small"].startswith("file://") for w in found)

    assert store.remove_folder(entry["id"]) is True
    assert store.folders() == []
    assert photos.is_dir()  # unlink only, files untouched


def test_scan_missing_folder_returns_empty(tmp_path):
    assert FavoritesStore.scan_folder(tmp_path / "missing") == []


def test_local_id_stable(tmp_path):
    target = tmp_path / "a.jpg"
    target.write_bytes(b"a")

    assert local_id(target) == local_id(str(target))
    assert local_id(target).startswith("file:")


def test_update_folder_settings(tmp_path):
    store = _store(tmp_path)
    photos = tmp_path / "photos"
    photos.mkdir()
    entry = store.add_folder(photos)

    assert store.update_folder_settings(entry["id"], slideshow=True) is True
    assert store.update_folder_settings(entry["id"], bogus=1) is True
    folders = store.folders()
    assert folders[0]["settings"]["slideshow"] is True
    assert "bogus" not in folders[0]["settings"]
    assert store.update_folder_settings("nope", slideshow=True) is False
