"""Local favorites store: collections of wallpapers on disk.

Keeps ``favorites.json`` next to ``config.json`` with the builtin
``favorites`` collection, user collections and linked photo folders.
Only wallpaper metadata is stored (id, urls, thumbnails) — never
binary blobs. Writes are atomic (temp file + replace); a corrupted
file is recreated with the default content, mirroring ``config``.
"""

import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List

from app.core import LoggerMixin

FAVORITES_FILE = "favorites.json"
FAVORITES_ID = "favorites"
FAVORITES_NAME = "Избранное"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}

DEFAULT_SETTINGS: Dict[str, Any] = {
    "slideshow": False,
    "interval": 300,
    "order": "sequential",
    "fit": "fill",
}

DEFAULT_COVER: Dict[str, Any] = {"mode": "heart"}


def local_id(path: Path | str) -> str:
    """Build a stable id for a local image file.

    Args:
        path: Image file path.

    Returns:
        ``file:``-prefixed resolved absolute path.
    """
    return "file:" + str(Path(path).expanduser().resolve())


def _new_id() -> str:
    """Generate a short unique collection id."""
    return uuid.uuid4().hex[:12]


def _builtin_favorites() -> Dict[str, Any]:
    """Return the always-present Favorites collection dict."""
    return {
        "id": FAVORITES_ID,
        "name": FAVORITES_NAME,
        "builtin": True,
        "cover": dict(DEFAULT_COVER),
        "settings": dict(DEFAULT_SETTINGS),
        "wallpapers": [],
    }


def _normalize_collection(raw: Any) -> Dict[str, Any] | None:
    """Coerce a raw dict into a collection, or None when broken.

    Missing keys are filled with defaults; wrong types reset the
    field instead of failing the whole file load.
    """
    if not isinstance(raw, dict):
        return None
    cid = raw.get("id")
    if not cid or not isinstance(cid, str):
        return None
    wallpapers = raw.get("wallpapers")
    if not isinstance(wallpapers, list):
        wallpapers = []
    wallpapers = [w for w in wallpapers if isinstance(w, dict)]
    settings = raw.get("settings")
    if not isinstance(settings, dict):
        settings = {}
    merged_settings = dict(DEFAULT_SETTINGS)
    merged_settings.update(
        {k: v for k, v in settings.items() if k in DEFAULT_SETTINGS}
    )
    cover = raw.get("cover")
    if not isinstance(cover, dict):
        cover = dict(DEFAULT_COVER)
    name = raw.get("name")
    if not name or not isinstance(name, str):
        name = cid
    return {
        "id": cid,
        "name": name,
        "builtin": bool(raw.get("builtin", False)),
        "cover": cover,
        "settings": merged_settings,
        "wallpapers": wallpapers,
    }


def _wid(wallpaper: Dict[str, Any]) -> str:
    """Return the identity key of a wallpaper dict."""
    wid = wallpaper.get("id", "")
    return str(wid) if wid else str(wallpaper.get("path", ""))


class FavoritesStore(LoggerMixin):
    """Load, persist and query local wallpaper collections."""

    def __init__(self, path: Path | str | None = None) -> None:
        super().__init__()
        self._path = Path(path) if path is not None else Path(
            FAVORITES_FILE
        )
        self._data = self._load_or_create()

    @property
    def path(self) -> Path:
        """Favorites file path."""
        return self._path

    # Persistence -------------------------------------------------

    def _default_data(self) -> Dict[str, Any]:
        """Return fresh default store content."""
        return {"collections": [_builtin_favorites()], "folders": []}

    def _load_or_create(self) -> Dict[str, Any]:
        """Load the store file, creating or recreating when needed."""
        if not self._path.exists():
            data = self._default_data()
            self._write(data)
            return data
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
            self._lg.warning(f"Favorites corrupted ({e}). Recreating.")
            data = self._default_data()
            self._write(data)
            return data
        return self._normalize(raw)

    def _normalize(self, raw: Any) -> Dict[str, Any]:
        """Coerce raw file content into valid store content."""
        if not isinstance(raw, dict):
            self._lg.warning("Favorites root is not an object.")
            return self._default_data()
        collections = []
        for item in raw.get("collections", []):
            norm = _normalize_collection(item)
            if norm is not None:
                collections.append(norm)
        if not any(c["id"] == FAVORITES_ID for c in collections):
            collections.insert(0, _builtin_favorites())
        folders = raw.get("folders", [])
        if not isinstance(folders, list):
            folders = []
        clean_folders = []
        for folder in folders:
            if not isinstance(folder, dict):
                continue
            settings = folder.get("settings")
            if not isinstance(settings, dict):
                settings = {}
            merged = dict(DEFAULT_SETTINGS)
            merged.update(
                {k: v for k, v in settings.items() if k in merged}
            )
            folder["settings"] = merged
            clean_folders.append(folder)
        return {"collections": collections, "folders": clean_folders}

    def _write(self, data: Dict[str, Any]) -> bool:
        """Atomically write store content to the file."""
        try:
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(data, indent=4, ensure_ascii=False),
                encoding="utf-8",
            )
            os.replace(tmp, self._path)
        except OSError as e:
            self._lg.error(f"Failed to save favorites: {e}.")
            return False
        return True

    def save(self) -> bool:
        """Persist the current in-memory content."""
        return self._write(self._data)

    def reload(self) -> None:
        """Re-read the store file, recreating when broken."""
        self._data = self._load_or_create()

    # Collections --------------------------------------------------

    def collections(self) -> List[Dict[str, Any]]:
        """Return all collections (builtin first)."""
        return list(self._data["collections"])

    def get(self, collection_id: str) -> Dict[str, Any] | None:
        """Return a collection by id, or None."""
        for collection in self._data["collections"]:
            if collection["id"] == collection_id:
                return collection
        return None

    def create(
        self,
        name: str,
        *,
        cover: Dict[str, Any] | None = None,
        settings: Dict[str, Any] | None = None,
    ) -> Dict[str, Any] | None:
        """Create a user collection, or None on empty name.

        Args:
            name: Collection display name.
            cover: Cover descriptor (defaults to last-added mode).
            settings: Initial settings subset.

        Returns:
            The created collection dict, or None.
        """
        name = (name or "").strip()
        if not name:
            return None
        merged = dict(DEFAULT_SETTINGS)
        if settings:
            merged.update(
                {k: v for k, v in settings.items() if k in merged}
            )
        collection = {
            "id": _new_id(),
            "name": name,
            "builtin": False,
            "cover": dict(cover) if cover else {"mode": "last"},
            "settings": merged,
            "wallpapers": [],
        }
        self._data["collections"].append(collection)
        if not self._write(self._data):
            self._data["collections"].pop()
            return None
        self._lg.info(f"Collection created: {name}.")
        return collection

    def rename(self, collection_id: str, name: str) -> bool:
        """Rename a collection (builtin included)."""
        name = (name or "").strip()
        if not name:
            return False
        collection = self.get(collection_id)
        if collection is None:
            return False
        collection["name"] = name
        return self._write(self._data)

    def delete(self, collection_id: str) -> bool:
        """Delete a user collection; builtin cannot be deleted."""
        if collection_id == FAVORITES_ID:
            return False
        before = len(self._data["collections"])
        self._data["collections"] = [
            c
            for c in self._data["collections"]
            if c["id"] != collection_id
        ]
        if len(self._data["collections"]) == before:
            return False
        self._lg.info(f"Collection deleted: {collection_id}.")
        return self._write(self._data)

    def clear(self, collection_id: str) -> bool:
        """Remove all wallpapers from a collection."""
        collection = self.get(collection_id)
        if collection is None:
            return False
        collection["wallpapers"] = []
        return self._write(self._data)

    # Wallpapers ----------------------------------------------------

    def add(
        self, collection_id: str, wallpaper: Dict[str, Any]
    ) -> bool:
        """Add a wallpaper unless already present (by id).

        Args:
            collection_id: Target collection id.
            wallpaper: Wallpaper dict (stored as a shallow copy).

        Returns:
            True when added, False on duplicate/missing/failed save.
        """
        collection = self.get(collection_id)
        if collection is None or not isinstance(wallpaper, dict):
            return False
        wid = _wid(wallpaper)
        if not wid:
            return False
        if any(_wid(w) == wid for w in collection["wallpapers"]):
            return False
        collection["wallpapers"].append(dict(wallpaper))
        if not self._write(self._data):
            collection["wallpapers"].pop()
            return False
        return True

    def remove(self, collection_id: str, wallpaper_id: str) -> bool:
        """Remove a wallpaper from a collection by id."""
        collection = self.get(collection_id)
        if collection is None:
            return False
        before = len(collection["wallpapers"])
        collection["wallpapers"] = [
            w for w in collection["wallpapers"] if _wid(w) != wallpaper_id
        ]
        if len(collection["wallpapers"]) == before:
            return False
        return self._write(self._data)

    def contains(self, collection_id: str, wallpaper_id: str) -> bool:
        """Return True when the collection holds the wallpaper id."""
        collection = self.get(collection_id)
        if collection is None:
            return False
        return any(
            _wid(w) == wallpaper_id for w in collection["wallpapers"]
        )

    # Cover and settings --------------------------------------------

    def set_cover(
        self, collection_id: str, cover: Dict[str, Any]
    ) -> bool:
        """Replace a collection cover descriptor."""
        collection = self.get(collection_id)
        if collection is None or not isinstance(cover, dict):
            return False
        collection["cover"] = dict(cover)
        return self._write(self._data)

    def update_settings(
        self, collection_id: str, **kwargs: Any
    ) -> bool:
        """Update known collection settings, ignoring unknown keys."""
        collection = self.get(collection_id)
        if collection is None:
            return False
        for key, value in kwargs.items():
            if key in DEFAULT_SETTINGS:
                collection["settings"][key] = value
        return self._write(self._data)

    def update_folder_settings(
        self, folder_id: str, **kwargs: Any
    ) -> bool:
        """Update known folder settings, ignoring unknown keys."""
        for folder in self._data["folders"]:
            if folder.get("id") != folder_id:
                continue
            settings = folder.get("settings")
            if not isinstance(settings, dict):
                settings = folder["settings"] = {}
            for key, value in kwargs.items():
                if key in DEFAULT_SETTINGS:
                    settings[key] = value
            return self._write(self._data)
        return False

    # Folders ----------------------------------------------------------

    def folders(self) -> List[Dict[str, Any]]:
        """Return linked photo folders."""
        return list(self._data["folders"])

    def add_folder(self, path: Path | str) -> Dict[str, Any] | None:
        """Link a photo folder (read-only collection source).

        The folder itself is never modified; unlinking only forgets
        it. Duplicate paths (resolved) are rejected.

        Args:
            path: Folder path to link.

        Returns:
            The folder entry, or None when missing/duplicate/failed.
        """
        folder = Path(path).expanduser()
        if not folder.is_dir():
            return None
        resolved = str(folder.resolve())
        if any(f.get("path") == resolved for f in self._data["folders"]):
            return None
        entry = {
            "id": _new_id(),
            "path": resolved,
            "name": folder.name or resolved,
            "settings": dict(DEFAULT_SETTINGS),
        }
        self._data["folders"].append(entry)
        if not self._write(self._data):
            self._data["folders"].pop()
            return None
        self._lg.info(f"Folder linked: {resolved}.")
        return entry

    def remove_folder(self, folder_id: str) -> bool:
        """Unlink a photo folder (files on disk are never touched)."""
        before = len(self._data["folders"])
        self._data["folders"] = [
            f for f in self._data["folders"] if f.get("id") != folder_id
        ]
        if len(self._data["folders"]) == before:
            return False
        return self._write(self._data)

    @staticmethod
    def scan_folder(path: Path | str) -> List[Dict[str, Any]]:
        """List image files of a folder as wallpaper dicts.

        Flat (non-recursive) scan; existence is re-checked on every
        call so deleted files simply disappear.

        Args:
            path: Folder path to scan.

        Returns:
            Wallpaper dicts with ``file:`` ids and ``file://`` thumbs.
        """
        folder = Path(path).expanduser()
        try:
            entries = sorted(folder.iterdir())
        except OSError:
            return []
        wallpapers = []
        for entry in entries:
            if not entry.is_file():
                continue
            if entry.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            uri = entry.resolve().as_uri()
            wallpapers.append(
                {
                    "id": local_id(entry),
                    "path": str(entry.resolve()),
                    "thumbs": {"small": uri},
                    "file_type": "file",
                }
            )
        return wallpapers
