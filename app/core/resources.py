"""Global registry of closable resources for a graceful shutdown."""

import asyncio
from typing import Awaitable, Callable

Closer = Callable[[], Awaitable[None]]

_closers: list[Closer] = []


def register(closer: Closer) -> None:
    """Register a resource closer invoked on application shutdown.

    Args:
        closer: Awaitable callable releasing a single resource.
    """
    _closers.append(closer)


async def close_all() -> None:
    """Await every registered closer in reverse registration order."""
    while _closers:
        closer = _closers.pop()
        await closer()


def run_close_all() -> None:
    """Close all registered resources from synchronous code."""
    asyncio.run(close_all())
