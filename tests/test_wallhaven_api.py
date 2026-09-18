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
async def test_search_raises_on_non_transient_http_error():
    """Non-transient failures (e.g. 500) raise so callers never mistake
    an error for an empty page (end of feed)."""
    api = make_client(lambda request: httpx.Response(500))
    with pytest.raises(httpx.HTTPError):
        await api.search_wallpapers()
    await api.close()


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
async def test_get_wallpaper_sends_apikey():
    """NSFW details must be requested with the API key."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"data": WALLPAPER})

    api = make_client(handler)
    await api.get_wallpaper("abc123")
    await api.close()

    assert seen["params"]["apikey"] == "test-key"


@pytest.mark.asyncio
async def test_get_wallpaper_returns_none_on_http_error():
    api = make_client(lambda request: httpx.Response(404))
    result = await api.get_wallpaper("abc123")
    await api.close()
    assert result is None


@pytest.mark.asyncio
async def test_get_wallpaper_caches_details():
    """Repeated detail requests for the same ID must not hit network."""
    detail = {**WALLPAPER, "tags": [{"name": "nature"}]}
    calls: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={"data": detail})

    api = make_client(handler)
    first = await api.get_wallpaper("abc123")
    second = await api.get_wallpaper("abc123")
    await api.close()

    assert first == detail
    assert second == detail
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_get_wallpaper_retries_transient_then_succeeds():
    """A transient 503 must be retried instead of returning None."""
    detail = {**WALLPAPER, "tags": [{"name": "nature"}]}
    responses = iter([httpx.Response(503), httpx.Response(200, json={"data": detail})])

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    api = make_client(handler)
    result = await api.get_wallpaper("abc123")
    await api.close()

    assert result == detail


def _capture_sleep(monkeypatch) -> list:
    """Replace asyncio.sleep with a recorder (no real waiting)."""
    delays: list = []

    async def _fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("app.service.wallhaven_api.asyncio.sleep", _fake_sleep)
    return delays


@pytest.mark.asyncio
async def test_search_retries_429_then_succeeds(monkeypatch):
    """A 429 must be retried (not raised immediately)."""
    calls: list = []
    responses = iter(
        [httpx.Response(429), httpx.Response(200, json={"data": [WALLPAPER]})]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return next(responses)

    api = make_client(handler)
    delays = _capture_sleep(monkeypatch)
    result = await api.search_wallpapers()
    await api.close()

    assert result == [WALLPAPER]
    assert len(calls) == 2
    assert len(delays) == 1


@pytest.mark.asyncio
async def test_search_honors_retry_after(monkeypatch):
    """Retry-After takes priority over the exponential backoff."""
    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": "2"}),
            httpx.Response(200, json={"data": [WALLPAPER]}),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    api = make_client(handler)
    delays = _capture_sleep(monkeypatch)
    result = await api.search_wallpapers()
    await api.close()

    assert result == [WALLPAPER]
    assert delays == [2.0]


@pytest.mark.asyncio
async def test_search_gives_up_after_max_retries(monkeypatch):
    """Exhausted transient retries raise; attempts are bounded."""
    calls: list = []
    api = make_client(
        lambda request: calls.append(request) or httpx.Response(503)
    )
    delays = _capture_sleep(monkeypatch)
    with pytest.raises(httpx.HTTPError):
        await api.search_wallpapers()
    await api.close()

    assert len(calls) == WallhavenAPI.MAX_RETRIES + 1
    assert len(delays) == WallhavenAPI.MAX_RETRIES


@pytest.mark.asyncio
async def test_get_wallpaper_honors_retry_after(monkeypatch):
    """A 429 with Retry-After sleeps exactly the header value."""
    detail = {**WALLPAPER, "tags": [{"name": "nature"}]}
    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": "2"}),
            httpx.Response(200, json={"data": detail}),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    api = make_client(handler)
    delays = _capture_sleep(monkeypatch)
    result = await api.get_wallpaper("abc123")
    await api.close()

    assert result == detail
    assert delays == [2.0]


@pytest.mark.asyncio
async def test_fetch_bytes_retries_transient_then_succeeds(monkeypatch):
    """fetch_bytes must retry transient errors like the other methods."""
    calls: list = []
    responses = iter([httpx.Response(503), httpx.Response(200, content=b"data")])

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return next(responses)

    api = make_client(handler)
    delays = _capture_sleep(monkeypatch)
    result = await api.fetch_bytes("https://example.com/w.jpg")
    await api.close()

    assert result == b"data"
    assert len(calls) == 2
    assert len(delays) == 1


@pytest.mark.asyncio
async def test_fetch_bytes_honors_retry_after(monkeypatch):
    """fetch_bytes sleeps the Retry-After value on 429."""
    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": "3"}),
            httpx.Response(200, content=b"data"),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    api = make_client(handler)
    delays = _capture_sleep(monkeypatch)
    result = await api.fetch_bytes("https://example.com/w.jpg")
    await api.close()

    assert result == b"data"
    assert delays == [3.0]


@pytest.mark.asyncio
async def test_get_wallpaper_cache_cleared_on_apik_change():
    """A new API key must drop cached detail responses."""
    detail = {**WALLPAPER, "tags": [{"name": "nature"}]}
    calls: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.params.get("apikey"))
        return httpx.Response(200, json={"data": detail})

    api = make_client(handler)
    await api.get_wallpaper("abc123")
    api.apik = "new-key"
    await api.get_wallpaper("abc123")
    await api.close()

    assert calls == ["test-key", "new-key"]


@pytest.mark.asyncio
async def test_get_wallpaper_evicts_lru_overflow():
    """The detail cache must not grow beyond its configured limit."""
    detail = {**WALLPAPER, "tags": [{"name": "nature"}]}
    calls: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={"data": detail})

    api = make_client(handler)
    api.DETAILS_CACHE_MAX = 1
    await api.get_wallpaper("one")
    await api.get_wallpaper("two")
    await api.get_wallpaper("one")
    await api.close()

    # "one" got evicted when "two" was stored, so it must be re-fetched.
    assert len(calls) == 3


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


@pytest.mark.asyncio
async def test_get_wallpaper_cache_expires_after_ttl():
    """Expired entry must trigger a refetch instead of serving stale cache."""
    first_detail = {**WALLPAPER, "tags": [{"name": "v1"}]}
    second_detail = {**WALLPAPER, "tags": [{"name": "v2"}]}
    calls: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        data = second_detail if len(calls) == 2 else first_detail
        return httpx.Response(200, json={"data": data})

    api = make_client(handler)
    first = await api.get_wallpaper("abc123")
    assert first == first_detail
    assert len(calls) == 1

    # Age the stored entry past TTL directly (no real waiting).
    ts, data = api._details_cache["abc123"]
    api._details_cache["abc123"] = (
        ts - (WallhavenAPI.DETAILS_CACHE_TTL + 100.0),
        data,
    )

    second = await api.get_wallpaper("abc123")
    await api.close()

    assert len(calls) == 2
    assert second == second_detail
    assert second != first


@pytest.mark.asyncio
async def test_get_wallpaper_returns_copy_not_alias():
    """Mutating a returned dict must not corrupt the cached entry."""
    detail = {**WALLPAPER, "tags": [{"name": "nature"}]}
    calls: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={"data": detail})

    api = make_client(handler)
    first = await api.get_wallpaper("abc123")
    first["tags"].append({"name": "evil"})
    first["id"] = "hacked"
    first["purity"] = "nsfw"

    second = await api.get_wallpaper("abc123")
    await api.close()

    assert len(calls) == 1
    assert second["id"] == "abc123"
    assert "purity" not in second
    assert second["tags"] == [{"name": "nature"}]
    assert all(t.get("name") != "evil" for t in second["tags"])


@pytest.mark.asyncio
async def test_cache_details_prunes_expired_on_set():
    """_cache_details must drop expired entries when storing a new one."""
    calls: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={"data": WALLPAPER})

    api = make_client(handler)
    stale_data = {"id": "stale-id", "tags": [{"name": "stale"}]}
    fresh_data = {"id": "fresh-id", "tags": [{"name": "fresh"}]}
    new_data = {"id": "new-id", "tags": [{"name": "new"}]}

    api._cache_details("stale-id", stale_data)
    api._cache_details("fresh-id", fresh_data)
    assert len(api._details_cache) == 2

    # Age only the stale entry past TTL (no real waiting).
    ts, data = api._details_cache["stale-id"]
    api._details_cache["stale-id"] = (
        ts - (WallhavenAPI.DETAILS_CACHE_TTL + 100.0),
        data,
    )

    api._cache_details("new-id", new_data)

    assert "stale-id" not in api._details_cache
    assert "fresh-id" in api._details_cache
    assert "new-id" in api._details_cache
    assert len(api._details_cache) == 2

    # Fresh entry must still be served from cache without network.
    fresh = await api.get_wallpaper("fresh-id")
    await api.close()

    assert fresh == fresh_data
    assert len(calls) == 0