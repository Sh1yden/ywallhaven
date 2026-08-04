"""Application entry point: run the Flet app in the configured mode."""

import logging
import json
import sys
import os

is_prod = False
try:
    with open("config.json", "r", encoding="utf-8") as f:
        if json.load(f).get("MODE") == "prod":
            is_prod = True
except Exception:
    pass

if is_prod or sys.stdout is None or sys.stderr is None:
    sys.stdout = open(os.devnull, "w")
    sys.stderr = open(os.devnull, "w")

from flet import run, AppView

from app.core import get_logger, config
from app.interface import flet_main

_lg = get_logger()


def cleanup():
    """Release resources before the application shutdown."""
    try:
        _lg.debug("Running cleaner: realeasing resources... 8)")

        _lg.debug("Trying to close api client from WallhavenAPI class...")

        _lg.debug("Success ;)")
    except Exception as e:
        _lg.error(f"Error during cleanup: {e}.")


def main():
    """Run the Flet app with the configured view and port."""
    try:
        _lg.info("Trying to run app...")
        _lg.debug(f"Config data is - {config.data}.")
        _lg.debug(f"Config root path is - {config._path}")
        _lg.debug("Success ;)")

        run(
            main=flet_main,
            view=AppView.FLET_APP,
            port=config.data.PORT,
        )

    except KeyboardInterrupt:
        _lg.info("Received exit signal (Ctrl+C).")
    except Exception as e:
        _lg.critical(f"Internal error: {e}.")
        raise e
    finally:
        logging.raiseExceptions = False

        try:
            cleanup()
            _lg.info("Bye, bye :(")

            sys.stdout.flush()
            sys.stderr.flush()
        except (BrokenPipeError, OSError):
            pass


if __name__ == "__main__":
    main()
