import inspect
import logging


def get_logger(name: str | None = None) -> logging.Logger:
    """Получить настроенный логгер для модуля монолита.

    Args:
        name: Имя логгера. Если None, используется имя вызывающего модуля.

    Returns:
        logging.Logger: Настроенный логгер с корректным пространством имен.
    """
    if name is None:
        frame = inspect.currentframe()
        if frame and frame.f_back:
            name = frame.f_back.f_globals.get("__name__", "unknown")

    root_prefix = "ywallhaven"

    # Если модуль запущен напрямую, заменяем __main__ на имя папки для красоты
    if name == "__main__":
        name = root_prefix
    elif name and not name.startswith(f"{root_prefix}."):
        # Если имя модуля уже начинается с "app.", не дублируем его
        if name.startswith("__main__."):
            name = name.replace("__main__.", f"{root_prefix}.", 1)
        else:
            name = f"{root_prefix}.{name}"

    return logging.getLogger(name)


class LoggerMixin:
    """Миксин для автоматической инициализации логгера внутри классов."""

    @property
    def _lg(self) -> logging.Logger:
        """Логгер, привязанный к конкретному модулю и классу."""
        if not hasattr(self, "_logger"):
            class_name = self.__class__.__name__
            module_name = self.__class__.__module__
            self._logger = get_logger(f"{module_name}.{class_name}")
        return self._logger
