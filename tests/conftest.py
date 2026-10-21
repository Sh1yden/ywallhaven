"""Shared pytest fixtures."""

import logging

import pytest


def _close_file_handlers() -> None:
    """Close file handlers left open by a test.

    Windows cannot remove an open log file, so ``tmp_path`` cleanup
    would fail without this. Console handlers are left untouched.
    """
    loggers = [logging.getLogger()]
    loggers.extend(
        value
        for value in logging.Logger.manager.loggerDict.values()
        if isinstance(value, logging.Logger)
    )
    for logger in loggers:
        for handler in list(logger.handlers):
            if isinstance(handler, logging.FileHandler):
                logger.removeHandler(handler)
                handler.close()

    # Some code drops a handler without closing it. Close any file
    # handler that still has a live reference, even if detached.
    for ref in list(getattr(logging, "_handlerList", ())):
        handler = ref()
        if isinstance(handler, logging.FileHandler):
            handler.close()


@pytest.fixture(autouse=True)
def _cleanup_file_handlers(tmp_path):
    """Close log files before pytest removes ``tmp_path``."""
    yield
    _close_file_handlers()
