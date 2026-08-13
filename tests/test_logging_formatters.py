"""Tests for the console/JSON log formatters and the setup helper."""

import json
import logging
import sys

from app.core.logger_config import (
    ColoredConsoleFormatter,
    JSONFormatter,
    setup_logging,
)


def _record(msg: str = "hello", exc_info=None) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test.module",
        level=logging.INFO,
        pathname="/path/to/file.py",
        lineno=1,
        msg=msg,
        args=None,
        exc_info=exc_info,
    )
    record.funcName = "some_func"
    return record


def test_json_formatter_fields() -> None:
    entry = json.loads(JSONFormatter().format(_record("hello")))

    assert entry["message"] == "hello"
    assert entry["level"] == "INFO"
    assert entry["def"] == "some_func"
    assert entry["filename"] == "file.py"
    assert entry["full_module"] == "test.module"
    assert isinstance(entry["pid"], int)
    assert entry["version"]
    assert len(entry["timestamp"]) == 23


def test_json_formatter_embeds_traceback() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        trace = sys.exc_info()

    entry = json.loads(JSONFormatter().format(_record(exc_info=trace)))

    assert "ValueError: boom" in entry["exception"]


def test_colored_console_formatter_contains_ansi() -> None:
    out = ColoredConsoleFormatter().format(_record())
    assert "INFO" in out
    assert "test.module" in out
    assert "\x1b[" in out
    assert "\033[0m" in out


def test_setup_logging_creates_indexed_files(tmp_path) -> None:
    setup_logging(level="INFO", log_dir=tmp_path, console=False, file=True)
    setup_logging(level="INFO", log_dir=tmp_path, console=False, file=True)

    logging.getLogger("ywallhaven.setup_test").info("probe")

    logs = sorted(tmp_path.glob("*.jsonl"))
    assert len(logs) == 2
    records = [
        json.loads(line)
        for log in logs
        for line in log.read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert any(entry["message"] == "probe" for entry in records)