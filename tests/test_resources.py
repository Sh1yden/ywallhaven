"""Tests for the closable resource registry."""

import asyncio

from app.core import resources


async def _closer(record: list[str], name: str):
    async def close() -> None:
        record.append(name)

    return close


def test_close_all_awaits_in_reverse_order() -> None:
    order: list[str] = []

    async def run() -> None:
        resources.register(await _closer(order, "a"))
        resources.register(await _closer(order, "b"))
        await resources.close_all()

    asyncio.run(run())

    assert order == ["b", "a"]


def test_close_all_is_safe_when_empty() -> None:
    assert asyncio.run(resources.close_all()) is None