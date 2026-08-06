"""Logging setup: colored console output and JSON file output."""

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
    """Configure the root application logger.

    Args:
        level: Logging level name (e.g. DEBUG, INFO).
        log_dir: Directory where log files are stored.
        console: Whether to attach a colored console handler.
        file: Whether to attach a JSON file handler.
    """

    log_dir.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger("ywallhaven")
    root_logger.setLevel(getattr(logging, level.upper()))

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

    root_logger.propagate = False

    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    for flet_logger_name in (
        "flet",
        "flet_core",
        "flet_desktop",
        "flet.messaging",
        "flet.controls",
        "flet.app",
    ):
        flet_logger = logging.getLogger(flet_logger_name)
        flet_logger.setLevel(getattr(logging, level.upper()))
        flet_logger.handlers.clear()
        if console:
            flet_logger.addHandler(console_handler)
        if file:
            flet_logger.addHandler(file_handler)
        flet_logger.propagate = False


class Colors:
    """ANSI colors for the terminal output."""

    RESET = "\033[0m"

    # Console log
    CURRENT_TIME_COLOR = "\u001b[34;1m"  # Light blue
    FILENAME_COLOR = "\u001b[32m"  # Green
    MODULE_COLOR = "\u001b[33m"  # Yellow
    CLASS_COLOR = "\u001b[34m"  # Light blue
    DEF_COLOR = "\u001b[36m"  # Blue
    MESSAGE_COLOR = "\u001b[37m"  # White

    # Log level
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    BRIGHT_RED = "\033[91m"


class ColoredConsoleFormatter(logging.Formatter):
    """Custom formatter for colored console output."""

    LEVEL_COLORS = {
        "DEBUG": Colors.CYAN,
        "INFO": Colors.GREEN,
        "WARNING": Colors.YELLOW,
        "ERROR": Colors.RED,
        "CRITICAL": Colors.BRIGHT_RED,
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a single colored line.

        Args:
            record: The log record to format.

        Returns:
            Formatted string with colored fields.
        """
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        level = record.levelname
        filename = os.path.basename(record.pathname) if record.pathname else None
        color = self.LEVEL_COLORS.get(record.levelname, Colors.RESET)

        full_module = record.name
        deff = record.funcName
        message = record.getMessage()

        colored_output = (
            f"{Colors.CURRENT_TIME_COLOR}{current_time}{Colors.RESET} | "
            f"{color}{level:<8}{Colors.RESET} | "
            f"{Colors.FILENAME_COLOR}{filename}{Colors.RESET} | "
            f"{Colors.MODULE_COLOR}{full_module}{Colors.RESET} | "
            f"{Colors.DEF_COLOR}{deff}{Colors.RESET} | "
            f"{message}"
        )

        return colored_output


class JSONFormatter(logging.Formatter):
    """JSON formatter for file log output."""

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a single JSON object.

        Args:
            record: The log record to format.

        Returns:
            JSON-encoded string with the record fields.
        """
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

        # Add traceback for errors
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)
