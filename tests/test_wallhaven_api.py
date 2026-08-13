"""Tests for the Wallhaven API client."""

import httpx
import pytest

from app.service import WallhavenAPI

WALLPAPER = {
    "id": "abc123",
    "file_type": "image/jpeg",
    "path": "https://w.wallhaven.cc/full/abc/wallhaven-abc123.jpg",
}


def make_client(handler) -> WallhavenAPI:
    """Build a WallhavenAPI client with a mocked transport."""
    api = WallhavenAPI(apik="test-key")
    api.client = httpx.AsyncClient(
        base_url=WallhavenAPI.BASE_URL,
        transport=httpx.MockTransport(handler),
    )
    return api


@pytest.mark.asyncio
async def test_search_returns_wallpapers():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"data": [WALLPAPER]})

    api = make_client(handler)
    result = await api.search_wallpapers(
        query="nature",
        page=2,
        sorting="relevance",
        atleast="1920x1080",
        resolutions="2560x1440",
        ratios="16x9",
        colors="660000",
        topRange="1M",
    )
    await api.close()

    assert result == [WALLPAPER]
    params = seen["params"]
    assert params["q"] == "nature"
    assert params["page"] == "2"
    assert params["sorting"] == "relevance"
    assert params["atleast"] == "1920x1080"
    assert params["resolutions"] == "2560x1440"
    assert params["ratios"] == "16x9"
    assert params["colors"] == "660000"
    assert params["topRange"] == "1M"
    assert params["apikey"] == "test-key"


@pytest.mark.asyncio
async def test_search_omits_empty_optional_params():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"data": []})

    api = make_client(handler)
    await api.search_wallpapers()
    await api.close()

    assert "atleast" not in seen["params"]
    assert "apikey" in seen["params"]


@pytest.mark.asyncio
async def test_search_returns_empty_list_on_http_error():
    api = make_client(lambda request: httpx.Response(500))
    result = await api.search_wallpapers()
    await api.close()
    assert result == []


@pytest.mark.asyncio
async def test_get_wallpaper_returns_data():
    detail = {**WALLPAPER, "tags": [{"name": "nature"}]}
    api = make_client(
        lambda request: httpx.Response(200, json={"data": detail})
    )
    result = await api.get_wallpaper("abc123")
    await api.close()
    assert result == detail


@pytest.mark.asyncio
async def test_get_wallpaper_returns_none_on_http_error():
    api = make_client(lambda request: httpx.Response(404))
    result = await api.get_wallpaper("abc123")
    await api.close()
    assert result is None


@pytest.mark.asyncio
async def test_fetch_bytes_returns_content():
    api = make_client(lambda request: httpx.Response(200, content=b"data"))
    result = await api.fetch_bytes("https://example.com/w.jpg")
    await api.close()
    assert result == b"data"


@pytest.mark.asyncio
async def test_fetch_bytes_returns_none_on_http_error():
    api = make_client(lambda request: httpx.Response(500))
    result = await api.fetch_bytes("https://example.com/w.jpg")
    await api.close()
    assert result is None


def test_build_filename_uses_extension_map():
    assert (
        WallhavenAPI.build_filename(
            {"id": "w1", "file_type": "image/png"}
        )
        == "w1.png"
    )
    assert (
        WallhavenAPI.build_filename(
            {"id": "w2", "file_type": "image/gif"}
        )
        == "w2.gif"
    )
    assert (
        WallhavenAPI.build_filename(
            {"id": "w3", "file_type": "image/webp"}
        )
        == "w3.webp"
    )


def test_build_filename_falls_back_to_jpg():
    assert (
        WallhavenAPI.build_filename(
            {"id": "w1", "file_type": "application/octet-stream"}
        )
        == "w1.jpg"
    )