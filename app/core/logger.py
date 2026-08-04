"""Logger helpers: module-aware get_logger and LoggerMixin."""

import inspect
import logging


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a configured logger for the given module.

    Args:
        name: Logger name. If None, the caller module name is used.

    Returns:
        Configured logger with a proper namespace.
    """
    if name is None:
        frame = inspect.currentframe()
        if frame and frame.f_back:
            name = frame.f_back.f_globals.get("__name__", "unknown")

    root_prefix = "ywallhaven"

    # If the module is run directly, replace __main__ with the root prefix
    if name == "__main__":
        name = root_prefix
    elif name and not name.startswith(f"{root_prefix}."):
        # If the module name already starts with the root prefix, keep it
        if name.startswith("__main__."):
            name = name.replace("__main__.", f"{root_prefix}.", 1)
        else:
            name = f"{root_prefix}.{name}"

    return logging.getLogger(name)


class LoggerMixin:
    """Mixin providing automatic logger initialization inside classes."""

    @property
    def _lg(self) -> logging.Logger:
        """Logger bound to the specific module and class."""
        if not hasattr(self, "_logger"):
            class_name = self.__class__.__name__
            module_name = self.__class__.__module__
            self._logger = get_logger(f"{module_name}.{class_name}")
        return self._logger
