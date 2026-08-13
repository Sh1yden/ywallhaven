"""Application entry point: run the Flet app in the configured mode."""

import logging
import json
import sys
import os
from pathlib import Path
from tempfile import gettempdir

from app.core.resources import run_close_all

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


_UPDATE_FILE_PATTERN = "ywallhaven-*-update.exe"
_UPDATER_LOG_LIMIT = 1_000_000


def _cleanup_update_files():
    """Remove leftover downloaded executables from the temp directory.

    Every successful update copies the new executable to its final
    location, so the temp copies are pure leftovers.
    """
    for path in Path(gettempdir()).glob(_UPDATE_FILE_PATTERN):
        try:
            path.unlink()
        except OSError:
            pass


def _trim_updater_log():
    """Drop the updater helper log when it grows beyond the limit."""
    log_path = Path(sys.executable).parent / "ywallhaven_updater.log"
    try:
        if log_path.is_file() and log_path.stat().st_size > _UPDATER_LOG_LIMIT:
            log_path.unlink()
    except OSError:
        pass


def cleanup():
    """Release resources before the application shutdown."""
    try:
        _lg.debug("Running cleaner: releasing resources... 8)")

        _lg.debug("Trying to close api clients...")
        run_close_all()
        _lg.debug("Api clients closed.")

        _lg.debug("Cleaning up leftover update files...")
        _cleanup_update_files()
        _trim_updater_log()

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
