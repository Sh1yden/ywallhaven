"""Global exception interception: sys/threading/asyncio hooks and a
UI handler guard so that failures always reach the application logs.
"""

import asyncio
import sys
import threading
from functools import wraps
from typing import Any, Callable, TypeVar

from app.core.logger import get_logger

F = TypeVar("F", bound=Callable[..., Any])


def install_exception_hooks() -> None:
    """Install the global sys and threading exception hooks.

    Idempotent: subsequent calls are no-ops.
    """
    if getattr(install_exception_hooks, "_installed", False):
        return
    install_exception_hooks._installed = True

    def _sys_hook(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: Any,
    ) -> None:
        get_logger("excepthook").critical(
            "Unhandled exception",
            exc_info=(exc_type, exc_value, exc_tb),
        )
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    def _thread_hook(args: threading.ExceptHookArgs) -> None:
        get_logger("threading.excepthook").error(
            "Unhandled thread exception",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = _sys_hook
    threading.excepthook = _thread_hook


def install_loop_exception_handler() -> None:
    """Attach an exception handler to the running asyncio event loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    def _handler(
        _loop: asyncio.AbstractEventLoop,
        context: dict[str, Any],
    ) -> None:
        logger = get_logger("asyncio")
        message = context.get("message", "Asyncio error")
        exc = context.get("exception")
        if exc is not None:
            logger.critical(message, exc_info=exc)
        else:
            logger.error(f"{message} (context: {context})")

    loop.set_exception_handler(_handler)


def guard(handler: F) -> F:
    """Wrap a UI event handler so exceptions are logged with a traceback.

    The exception is re-raised afterwards so Flet keeps its normal
    error reporting flow as a fallback.
    """

    @wraps(handler)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return handler(*args, **kwargs)
        except Exception as e:
            get_logger("ui").error(
                f"Handler {handler.__qualname__} failed: {e}",
                exc_info=True,
            )
            raise

    return wrapper  # type: ignore[return-value]