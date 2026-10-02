"""Live smoke check for the Wallhaven API (no mocks).

Run manually before a release or on a schedule to learn that
wallhaven.cc itself is down without launching the GUI:

    uv run python scripts/smoke_wallhaven.py

Exit code 0 means the API answered, 1 means it did not. This file
is intentionally kept out of tests/ so unit runs never touch the
network.
"""

import asyncio
import sys

sys.path.insert(0, ".")

from app.service import WallhavenAPI


async def main() -> int:
    """Hit search plus one detail request and report HTTP outcomes."""
    api = WallhavenAPI()
    try:
        items = await api.search_wallpapers(query="nature", page=1)
    except Exception as e:
        print(f"SMOKE FAIL: /search raised: {e}")
        return 1
    finally:
        await api.close()
    print(f"SMOKE OK: /search returned {len(items)} items")
    if not items:
        print("SMOKE WARN: empty feed, nothing to check details with")
        return 0
    first_id = items[0].get("id", "")
    api2 = WallhavenAPI()
    try:
        detail = await api2.get_wallpaper(first_id)
    except Exception as e:
        print(f"SMOKE FAIL: /w raised: {e}")
        return 1
    finally:
        await api2.close()
    if not detail:
        print("SMOKE FAIL: /w returned no detail")
        return 1
    print(f"SMOKE OK: /w/{first_id} has detail")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
