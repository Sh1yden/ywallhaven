"""Модуль запуска приложения."""

from app.core import get_logger, config


async def main():
    # Test logger and settings...
    _lg = get_logger()
    _lg.debug(f"APIK: {config.data.APIK}")
    _lg.debug(f"LOG_LVL: {config.data.LOG_LVL}")


if __name__ == "__main__":
    from asyncio import run

    run(main())
