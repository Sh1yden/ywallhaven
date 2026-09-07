"""Async client for the Wallhaven public API v1."""

import asyncio
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional

from httpx import AsyncClient, HTTPError

from app.core import LoggerMixin, config


class WallhavenAPI(LoggerMixin):
    """Async HTTP client for the Wallhaven search endpoint."""

    BASE_URL = "https://wallhaven.cc/api/v1"

    FILE_EXTENSIONS = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/bmp": ".bmp",
    }

    TRANSIENT_STATUSES = (429, 502, 503, 504)
    DETAILS_CACHE_MAX = 256

    def __init__(self, apik: str | None = None) -> None:
        super().__init__()
        self._apik: str | None = None
        self._details_cache: OrderedDict[str, Dict[str, Any]] = (
            OrderedDict()
        )
        self.client = AsyncClient(base_url=self.BASE_URL, timeout=15.0)
        self.apik = apik or config.data.APIK

    @property
    def apik(self) -> str | None:
        """Wallhaven API key used for NSFW-capable requests."""
        return self._apik

    @apik.setter
    def apik(self, value: str | None) -> None:
        """Set the API key, dropping cached details on key change.

        Purity visibility and returned tags depend on the key, so detail
        responses fetched under an old key must not be reused.
        """
        if value != self._apik:
            self._details_cache.clear()
        self._apik = value

    async def close(self):
        """Close the underlying HTTP client session."""
        await self.client.aclose()

    async def search_wallpapers(
        self,
        query: Optional[str] = "",
        page: int = 1,
        categories: Optional[str] = "111",
        purity: Optional[str] = "100",
        sorting: Optional[str] = "date_added",
        order: Optional[str] = "desc",
        atleast: Optional[str] = "",
        resolutions: Optional[str] = "",
        ratios: Optional[str] = "",
        colors: Optional[str] = "",
        topRange: Optional[str] = "",
    ) -> List[Dict[str, Any]]:
        """Search wallpapers matching the given filters.

        Args:
            query: Search query string.
            page: Page number to fetch.
            categories: Category flags ("111" for all).
            purity: Purity filter flags ("100" for SFW only).
            sorting: Sort method: date_added, relevance, random,
                views, favorites, toplist.
            order: Sort order: desc or asc.
            atleast: Minimum resolution (e.g. "1920x1080").
            resolutions: Comma-separated exact resolutions.
            ratios: Comma-separated aspect ratios (e.g. "16x9").
            colors: Hex color without "#" (e.g. "660000").
            topRange: Toplist range (1d, 1w, 1M, ...); used with
                sorting="toplist".

        Returns:
            List of wallpaper dicts, or an empty list on failure.
        """
        params = {
            "q": query,
            "page": page,
            "categories": categories,
            "purity": purity,
            "sorting": sorting,
            "order": order,
        }

        for name, value in (
            ("atleast", atleast),
            ("resolutions", resolutions),
            ("ratios", ratios),
            ("colors", colors),
            ("topRange", topRange),
        ):
            if value:
                params[name] = value

        self._lg.debug(f"params is - {params}.")

        if self.apik:
            params["apikey"] = self.apik

        try:
            start = time.perf_counter()
            response = await self.client.get("/search", params=params)
            response.raise_for_status()
            elapsed_ms = (time.perf_counter() - start) * 1000
            payload = response.json()
            items = payload.get("data", []) if isinstance(payload, dict) else []
            self._lg.debug(f"All response {payload}")
            self._lg.debug(
                f"Wallhaven returned {len(items)} items in "
                f"{elapsed_ms:.0f} ms ({len(response.content)} bytes)."
            )
            return items
        except HTTPError as e:
            # Transient 502/503/429 should be retried, not treated as "no more"
            status = getattr(getattr(e, "response", None), "status_code", 0)
            if status in self.TRANSIENT_STATUSES:
                self._lg.warning(
                    f"Transient Wallhaven error {status}: {e} — will retry"
                )
                raise
            self._lg.error(f"Error by req to Wallhaven: {e}.")
            return []

    async def get_wallpaper(
        self, wallpaper_id: str, retries: int = 2
    ) -> Dict[str, Any] | None:
        """Fetch a single wallpaper by its ID including its tags.

        The search endpoint response does not contain tags, so a detail
        request is needed to render the clickable tag chips. Successful
        responses are cached per ID (LRU) so revisiting a wallpaper
        (grid re-click or fullscreen navigation) is instant. Transient
        errors (429/502/503/504) are retried with a short backoff.

        Args:
            wallpaper_id: Wallhaven wallpaper ID.
            retries: Number of follow-up attempts after a transient error.

        Returns:
            Wallpaper dict including tags, or None on failure.
        """
        cached = self._details_cache.get(wallpaper_id)
        if cached is not None:
            self._details_cache.move_to_end(wallpaper_id)
            return cached

        params: Dict[str, Any] = {}
        if self.apik:
            params["apikey"] = self.apik

        for attempt in range(retries + 1):
            try:
                start = time.perf_counter()
                response = await self.client.get(
                    f"/w/{wallpaper_id}", params=params
                )
                response.raise_for_status()
                elapsed_ms = (time.perf_counter() - start) * 1000
                self._lg.debug(
                    f"Fetched wallpaper {wallpaper_id} in "
                    f"{elapsed_ms:.0f} ms ({len(response.content)} bytes)."
                )
                data = response.json().get("data")
                if data:
                    self._cache_details(wallpaper_id, data)
                return data
            except HTTPError as e:
                status = getattr(
                    getattr(e, "response", None), "status_code", 0
                )
                if status in self.TRANSIENT_STATUSES and attempt < retries:
                    self._lg.warning(
                        f"Transient Wallhaven error {status} while "
                        f"fetching {wallpaper_id}, retry "
                        f"{attempt + 1}/{retries}: {e}"
                    )
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                self._lg.error(
                    f"Failed to fetch wallpaper {wallpaper_id}: {e}."
                )
                break
        return None

    def _cache_details(
        self, wallpaper_id: str, data: Dict[str, Any]
    ) -> None:
        """Store a detail response, evicting the oldest on overflow.

        Args:
            wallpaper_id: Wallhaven wallpaper ID.
            data: Wallpaper detail dict from the API.
        """
        self._details_cache[wallpaper_id] = data
        self._details_cache.move_to_end(wallpaper_id)
        while len(self._details_cache) > self.DETAILS_CACHE_MAX:
            self._details_cache.popitem(last=False)

    async def fetch_bytes(self, url: str) -> bytes | None:
        """Download a wallpaper file content as bytes.

        Args:
            url: Full-size wallpaper URL (the "path" field).

        Returns:
            File content bytes, or None on failure.
        """
        try:
            start = time.perf_counter()
            response = await self.client.get(url)
            response.raise_for_status()
            elapsed_ms = (time.perf_counter() - start) * 1000
            self._lg.debug(
                f"Downloaded image bytes in {elapsed_ms:.0f} ms "
                f"({len(response.content)} bytes)."
            )
            return response.content
        except HTTPError as e:
            self._lg.error(f"Failed to download {url}: {e}.")
            return None

    @staticmethod
    def build_filename(wallpaper: Dict[str, Any]) -> str:
        """Build a file name for a wallpaper.

        Args:
            wallpaper: Wallpaper dict from the API.

        Returns:
            File name with the proper extension.
        """
        ext = WallhavenAPI.FILE_EXTENSIONS.get(
            wallpaper.get("file_type", ""), ".jpg"
        )
        return f"{wallpaper.get('id', 'wallpaper')}{ext}"

    async def __aenter__(self) -> "WallhavenAPI":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()
