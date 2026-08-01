import inspect
import logging
import os
import sys
from datetime import datetime
from pathlib import Path


def setup_logging(
    level: str = "DEBUG",
    log_dir: Path = Path("logs"),
    console: bool = True,
    file: bool = True,
) -> None:
    """
    Настройка корневого логгера приложения.
    Вызывается один раз при старте.
    """

    log_dir.mkdir(parents=True, exist_ok=True)

    # Корневой логгер приложения
    root_logger = logging.getLogger("ywallhaven")
    root_logger.setLevel(getattr(logging, level.upper()))

    # Очищаем существующие хендлеры
    root_logger.handlers.clear()

    # === CONSOLE HANDLER ===
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_formatter = ColoredConsoleFormatter()
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

    # === FILE HANDLER ===
    if file:
        log_filename = f"{datetime.now().strftime('%Y-%m-%d')}-01.jsonl"
        log_filepath = log_dir / log_filename

        # Найти свободный номер файла
        counter = 1
        while log_filepath.exists():
            counter += 1
            log_filename = f"{datetime.now().strftime('%Y-%m-%d')}-{counter:02d}.jsonl"
            log_filepath = log_dir / log_filename

        file_handler = logging.FileHandler(log_filepath, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        json_formatter = JSONFormatter()
        file_handler.setFormatter(json_formatter)
        root_logger.addHandler(file_handler)

    # Отключаем пропагацию в root логгер Python
    root_logger.propagate = False

    # Настраиваем логгеры библиотек
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


class Colors:
    """ANSI цвета для терминала"""

    RESET = "\033[0m"

    # CONSOLE LOG
    CURRENT_TIME_COLOR = "\u001b[34;1m"  # Светло синий
    FILENAME_COLOR = "\u001b[32m"  # Зелёный
    MODULE_COLOR = "\u001b[33m"  # Желтый
    CLASS_COLOR = "\u001b[34m"  # Голубой
    DEF_COLOR = "\u001b[36m"  # Синий
    MESSAGE_COLOR = "\u001b[37m"  # Белый

    # LOG LVL
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    BRIGHT_RED = "\033[91m"


class ColoredConsoleFormatter(logging.Formatter):
    """Кастомный форматтер для цветного вывода в консоль"""

    LEVEL_COLORS = {
        "DEBUG": Colors.CYAN,
        "INFO": Colors.GREEN,
        "WARNING": Colors.YELLOW,
        "ERROR": Colors.RED,
        "CRITICAL": Colors.BRIGHT_RED,
    }

    def format(self, record: logging.LogRecord) -> str:
        stack = inspect.stack()
        caller_frame = stack[2].frame

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        level = record.levelname
        filename = os.path.basename(record.pathname) if record.pathname else None
        color = self.LEVEL_COLORS.get(record.levelname, Colors.RESET)

        full_module = record.name
        module = record.module
        # module = inspect.getmodule(
        #     caller_frame
        # ).__name__  # pyright: ignore[reportOptionalMemberAccess]
        cls_obj = caller_frame.f_locals.get("self", None)
        # cls_name = cls_obj.__class__.__name__ if cls_obj else None
        deff = record.funcName
        message = record.getMessage()

        colored_output = (
            f"{Colors.CURRENT_TIME_COLOR}{current_time}{Colors.RESET} | "
            f"{color}{level:<8}{Colors.RESET} | "
            f"{Colors.FILENAME_COLOR}{filename}{Colors.RESET} | "
            f"{Colors.MODULE_COLOR}{full_module}{Colors.RESET} | "
            # f"{Colors.MODULE_COLOR}{module}{Colors.RESET} | "
            # f"{Colors.CLASS_COLOR}{cls_name}{Colors.RESET} | "
            f"{Colors.DEF_COLOR}{deff}{Colors.RESET} | "
            f"{message}"
        )

        return colored_output


class JSONFormatter(logging.Formatter):
    """JSON форматтер"""

    def format(self, record: logging.LogRecord) -> str:
        import json

        filename = os.path.basename(record.pathname) if record.pathname else None

        log_entry = {
            "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "level": record.levelname,
            "filename": filename,
            "full_module": record.name,
            "def": record.funcName,
            "message": record.getMessage(),
        }

        # Добавляем traceback при ошибках
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)
