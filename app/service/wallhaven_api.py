"""Async client for the Wallhaven public API v1."""

import asyncio
import random
import time
from collections import OrderedDict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
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
    MAX_RETRIES = 3
    BASE_DELAY = 0.5
    MAX_DELAY = 8.0
    DETAILS_CACHE_TTL = 900.0

    def __init__(self, apik: str | None = None) -> None:
        super().__init__()
        self._apik: str | None = None
        self._details_cache: OrderedDict[str, tuple[float, Dict[str, Any]]] = (
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

    @staticmethod
    def _status_of(exc: HTTPError) -> int | None:
        """Extract the HTTP status code from an httpx error.

        Returns:
            The response status code, or None when the error carries
            no response (timeouts, connection errors).
        """
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
        return status if isinstance(status, int) else None

    def _is_transient(self, exc: HTTPError) -> bool:
        """Check whether an error is worth retrying.

        Uses the single TRANSIENT_STATUSES tuple. Errors without a
        response (timeouts, connection drops) are treated as transient
        since no status is available to judge them by.
        """
        status = self._status_of(exc)
        if status is None:
            return True
        return status in self.TRANSIENT_STATUSES

    def _retry_delay(self, exc: HTTPError, attempt: int) -> float:
        """Compute the delay before retry `attempt` (0-based).

        The Retry-After response header (seconds or HTTP-date) wins
        when present; otherwise exponential backoff with jitter.
        X-RateLimit headers are surfaced to the debug log.

        Args:
            exc: The failed request error.
            attempt: Zero-based retry attempt number.

        Returns:
            Delay in seconds, clamped to MAX_DELAY.
        """
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None)
        if headers is not None:
            try:
                remaining = headers.get("X-RateLimit-Remaining")
            except Exception:
                remaining = None
            if remaining is not None:
                self._lg.debug(f"Rate limit remaining: {remaining}.")
            try:
                raw = headers.get("Retry-After")
            except Exception:
                raw = None
            if raw is not None:
                retry_after = self._parse_retry_after(str(raw).strip())
                if retry_after is not None:
                    return min(retry_after, self.MAX_DELAY)
        backoff = self.BASE_DELAY * (2**attempt)
        jitter = random.uniform(0, self.BASE_DELAY)
        return min(backoff + jitter, self.MAX_DELAY)

    @staticmethod
    def _parse_retry_after(raw: str) -> float | None:
        """Parse a Retry-After header value into seconds.

        Args:
            raw: Header value — delay seconds or an HTTP-date.

        Returns:
            Delay in seconds, or None when unparseable.
        """
        try:
            delay = float(raw)
            return delay if delay >= 0 else None
        except (ValueError, TypeError):
            pass
        try:
            moment = parsedate_to_datetime(raw)
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
            delta = (moment - datetime.now(timezone.utc)).total_seconds()
            return max(0.0, delta)
        except (ValueError, TypeError, OverflowError):
            return None

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
            List of wallpaper dicts. An empty list means the page
            genuinely has no items — request failures raise instead,
            so callers never confuse an error with the end of feed.

        Raises:
            httpx.HTTPError: On request failure. Transient errors
                (TRANSIENT_STATUSES, network failures) are retried
                with Retry-After-aware backoff before giving up.
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

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                start = time.perf_counter()
                response = await self.client.get("/search", params=params)
                response.raise_for_status()
                elapsed_ms = (time.perf_counter() - start) * 1000
                payload = response.json()
                items = (
                    payload.get("data", []) if isinstance(payload, dict) else []
                )
                self._lg.debug(f"All response {payload}")
                self._lg.debug(
                    f"Wallhaven returned {len(items)} items in "
                    f"{elapsed_ms:.0f} ms ({len(response.content)} bytes)."
                )
                return items
            except HTTPError as e:
                if not self._is_transient(e) or attempt >= self.MAX_RETRIES:
                    self._lg.error(f"Search request failed: {e}.")
                    raise
                delay = self._retry_delay(e, attempt)
                self._lg.warning(
                    f"Transient Wallhaven error {self._status_of(e)} "
                    f"on /search (attempt {attempt + 1}/"
                    f"{self.MAX_RETRIES}), retrying in "
                    f"{delay:.2f}s: {e}"
                )
                await asyncio.sleep(delay)

    async def get_wallpaper(
        self, wallpaper_id: str, retries: int | None = None
    ) -> Dict[str, Any] | None:
        """Fetch a single wallpaper by its ID including its tags.

        The search endpoint response does not contain tags, so a detail
        request is needed to render the clickable tag chips. Successful
        responses are cached per ID (LRU) so revisiting a wallpaper
        (grid re-click or fullscreen navigation) is instant. Transient
        errors are retried with Retry-After-aware backoff.

        Args:
            wallpaper_id: Wallhaven wallpaper ID.
            retries: Number of follow-up attempts after a transient
                error (defaults to MAX_RETRIES).

        Returns:
            Wallpaper dict including tags, or None on failure.
        """
        if retries is None:
            retries = self.MAX_RETRIES
        cached = self._details_cache.get(wallpaper_id)
        if cached is not None:
            ts, data = cached
            if time.monotonic() - ts > self.DETAILS_CACHE_TTL:
                del self._details_cache[wallpaper_id]
            else:
                self._details_cache.move_to_end(wallpaper_id)
                return self._copy_details(data)

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
                    return self._copy_details(data)
                return data
            except HTTPError as e:
                if self._is_transient(e) and attempt < retries:
                    delay = self._retry_delay(e, attempt)
                    self._lg.warning(
                        f"Transient Wallhaven error {self._status_of(e)} "
                        f"while fetching {wallpaper_id}, retry "
                        f"{attempt + 1}/{retries} in {delay:.2f}s: {e}"
                    )
                    await asyncio.sleep(delay)
                    continue
                self._lg.error(
                    f"Failed to fetch wallpaper {wallpaper_id}: {e}."
                )
                break
        return None

    @staticmethod
    def _copy_details(data: Dict[str, Any]) -> Dict[str, Any]:
        """Return a shallow copy decoupled from the cache entry.

        Copies the top-level dict and the ``tags`` list so callers
        mutating ``wallpaper["tags"]`` (e.g. right panel) cannot
        corrupt the cached response.
        """
        copy = dict(data)
        tags = copy.get("tags")
        if isinstance(tags, list):
            copy["tags"] = list(tags)
        return copy

    def _cache_details(
        self, wallpaper_id: str, data: Dict[str, Any]
    ) -> None:
        """Store a detail response with TTL, evicting oldest on overflow.

        Args:
            wallpaper_id: Wallhaven wallpaper ID.
            data: Wallpaper detail dict from the API.
        """
        now = time.monotonic()
        for key, (ts, _) in list(self._details_cache.items()):
            if now - ts > self.DETAILS_CACHE_TTL:
                del self._details_cache[key]
        self._details_cache[wallpaper_id] = (now, self._copy_details(data))
        self._details_cache.move_to_end(wallpaper_id)
        while len(self._details_cache) > self.DETAILS_CACHE_MAX:
            self._details_cache.popitem(last=False)

    async def fetch_bytes(self, url: str) -> bytes | None:
        """Download a wallpaper file content as bytes.

        Transient errors are retried with Retry-After-aware backoff.

        Args:
            url: Full-size wallpaper URL (the "path" field).

        Returns:
            File content bytes, or None on failure.
        """
        for attempt in range(self.MAX_RETRIES + 1):
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
                if self._is_transient(e) and attempt < self.MAX_RETRIES:
                    delay = self._retry_delay(e, attempt)
                    self._lg.warning(
                        f"Transient error downloading {url}, retry "
                        f"{attempt + 1}/{self.MAX_RETRIES} in "
                        f"{delay:.2f}s: {e}"
                    )
                    await asyncio.sleep(delay)
                    continue
                self._lg.error(f"Failed to download {url}: {e}.")
                return None
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
