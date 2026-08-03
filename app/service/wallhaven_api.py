from typing import Any, Dict, List, Optional

from httpx import AsyncClient, HTTPError

from app.core import LoggerMixin, config


class WallhavenAPI(LoggerMixin):
    BASE_URL = "https://wallhaven.cc/api/v1"

    def __init__(self, apik: str | None = None) -> None:
        super().__init__()
        self.apik = apik or config.data.APIK
        self.client = AsyncClient(base_url=self.BASE_URL, timeout=15.0)

    async def close(self):
        await self.client.aclose()

    async def search_wallpapers(
        self,
        query: Optional[str] = "",
        page: int = 1,
        categories: Optional[str] = "111",
        purity: Optional[str] = "100",
    ) -> List[Dict[str, Any]]:
        params = {
            "q": query,
            "page": page,
            "categories": categories,
            "purity": purity,
        }

        self._lg.debug(f"params is - {params}.")

        if self.apik:
            params["apikey"] = self.apik

        try:
            response = await self.client.get("/search", params=params)
            response.raise_for_status()
            self._lg.debug(
                f"Wallhaven returned {len(response.json().get('data', []))} items."
            )
            return response.json().get("data", [])
        except HTTPError as e:
            self._lg.error(f"Error by req to Wallhaven: {e}.")
            return []

    async def __aenter__(self) -> "WallhavenAPI":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()
