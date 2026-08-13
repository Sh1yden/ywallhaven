"""Tests for the global exception interception helpers."""

import asyncio
import logging
import sys
import threading

import pytest

from app.core.error_handling import (
    guard,
    install_exception_hooks,
    install_loop_exception_handler,
)


def _records_for(name: str) -> tuple[list[logging.LogRecord], logging.Handler]:
    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append
    logger = logging.getLogger(name)
    logger.addHandler(handler)
    return records, handler


def test_guard_logs_and_reraises() -> None:
    records, handler = _records_for("ywallhaven.ui")
    try:

        @guard
        def failing() -> None:
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            failing()
    finally:
        logging.getLogger("ywallhaven.ui").removeHandler(handler)

    assert any("failed: boom" in record.getMessage() for record in records)


def test_guard_returns_value() -> None:
    @guard
    def ok() -> int:
        return 42

    assert ok() == 42


def test_install_exception_hooks_replaces_and_passes_through(
    monkeypatch,
) -> None:
    old_sys, old_thread = sys.excepthook, threading.excepthook
    seen: dict[str, bool] = {}
    monkeypatch.setattr(
        sys, "__excepthook__", lambda *_: seen.setdefault("called", True)
    )
    try:
        install_exception_hooks()
        assert sys.excepthook is not old_sys
        assert threading.excepthook is not old_thread

        sys.excepthook(ValueError, ValueError("boom"), None)
        assert seen["called"] is True

        first = sys.excepthook
        install_exception_hooks()
        assert sys.excepthook is first
    finally:
        sys.excepthook = old_sys
        threading.excepthook = old_thread


def test_loop_handler_without_running_loop() -> None:
    assert install_loop_exception_handler() is None


def test_loop_handler_reports_exception_context() -> None:
    records, handler = _records_for("ywallhaven.asyncio")

    async def run() -> None:
        loop = asyncio.get_running_loop()
        install_loop_exception_handler()
        loop.call_exception_handler(
            {"message": "boom", "exception": ValueError("x")}
        )

    try:
        asyncio.run(run())
    finally:
        logging.getLogger("ywallhaven.asyncio").removeHandler(handler)

    assert records, "loop exception handler did not log anything"


def test_loop_handler_reports_bare_context() -> None:
    records, handler = _records_for("ywallhaven.asyncio")

    async def run() -> None:
        loop = asyncio.get_running_loop()
        install_loop_exception_handler()
        loop.call_exception_handler({"message": "boom"})

    try:
        asyncio.run(run())
    finally:
        logging.getLogger("ywallhaven.asyncio").removeHandler(handler)

    assert records