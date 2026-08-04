"""Async client for the Wallhaven public API v1."""

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

    def __init__(self, apik: str | None = None) -> None:
        super().__init__()
        self.apik = apik or config.data.APIK
        self.client = AsyncClient(base_url=self.BASE_URL, timeout=15.0)

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
            response = await self.client.get("/search", params=params)
            response.raise_for_status()
            self._lg.debug(f"All response {response.json()}")
            self._lg.debug(
                f"Wallhaven returned {len(response.json().get('data', []))} items."
            )
            return response.json().get("data", [])
        except HTTPError as e:
            self._lg.error(f"Error by req to Wallhaven: {e}.")
            return []

    async def fetch_bytes(self, url: str) -> bytes | None:
        """Download a wallpaper file content as bytes.

        Args:
            url: Full-size wallpaper URL (the "path" field).

        Returns:
            File content bytes, or None on failure.
        """
        try:
            response = await self.client.get(url)
            response.raise_for_status()
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
