"""Standalone updater helper: replace a running executable and restart.

Invoked by the running application as ``ywallhaven-updater.exe
--pid <pid> --src <new-exe> --dst <target-exe> [--log <path>]
[--restart]``. The helper waits for the target process to exit
(because Windows locks a running executable), atomically replaces the
target file and optionally starts the new version.
"""

import argparse
import ctypes
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

WAIT_POLL_SECONDS = 0.5
WAIT_TIMEOUT_SECONDS = 60.0

STILL_ACTIVE = 259  # Windows GetExitCodeProcess constant


def _parse_args() -> argparse.Namespace:
    """Parse the updater command line arguments.

    Returns:
        Parsed namespace with pid, src, dst, log and restart flags.
    """
    parser = argparse.ArgumentParser(description="ywallhaven updater helper")
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--src", type=Path, required=True)
    parser.add_argument("--dst", type=Path, required=True)
    parser.add_argument("--log", type=Path, default=None)
    parser.add_argument("--restart", action="store_true")
    return parser.parse_args()


def _setup_logger(args: argparse.Namespace) -> logging.Logger:
    """Create a file logger next to the target executable.

    Args:
        args: Parsed command line arguments.

    Returns:
        Configured logger.
    """
    log_path = args.log or args.dst.parent / "ywallhaven_updater.log"
    logger = logging.getLogger("ywallhaven-updater")
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    return logger


def _process_alive(pid: int) -> bool:
    """Return True while the given process id is still running.

    Args:
        pid: Process id to probe.

    Returns:
        True when the process exists, False otherwise.
    """
    if sys.platform == "win32":
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return True
            return exit_code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)

    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _wait_for_exit(pid: int, timeout: float, logger: logging.Logger) -> bool:
    """Poll until the given process exits or the timeout is reached.

    Args:
        pid: Process id to wait for.
        timeout: Maximum number of seconds to wait.
        logger: Logger for status messages.

    Returns:
        True when the process exited in time, False otherwise.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _process_alive(pid):
            if logger is not None:
                logger.info(f"Process {pid} exited; proceeding.")
            return True
        time.sleep(WAIT_POLL_SECONDS)
    return False


def _restart(dst: Path, logger: logging.Logger) -> None:
    """Launch the replaced application detached from this process.

    Args:
        dst: Path of the replaced executable.
        logger: Logger for status messages.
    """
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS, CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [str(dst)],
        cwd=str(dst.parent),
        creationflags=flags,
        close_fds=True,
    )
    logger.info(f"Restarted {dst}.")


def main() -> int:
    """Run the updater routine.

    Returns:
        Process exit code: 0 on success, non-zero on failure.
    """
    args = _parse_args()
    logger = _setup_logger(args)
    logger.info(
        f"Updater started: pid={args.pid}, src={args.src}, dst={args.dst}."
    )

    if not args.src.is_file():
        logger.error(f"Source file missing: {args.src}")
        try:
            parent = args.src.parent
            existing = list(parent.glob("ywallhaven-*-update.exe"))
            logger.error(f"Src parent listing: {existing}")
            logger.error(f"Src resolve: {args.src.resolve() if args.src.exists() else 'no resolve'}")
        except Exception as ex:
            logger.error(f"Failed to list src parent: {ex}")
        return 1

    if not _wait_for_exit(args.pid, WAIT_TIMEOUT_SECONDS, logger):
        logger.error(f"Process {args.pid} did not exit in "
                     f"{WAIT_TIMEOUT_SECONDS:.0f}s; aborting.")
        return 2

    # Log dst access before replace (helps diagnose WinError 5)
    try:
        exists = args.dst.exists()
        writable = os.access(args.dst, os.W_OK) if exists else os.access(args.dst.parent, os.W_OK)
        logger.info(f"Dst check: exists={exists}, writable={writable}, dst={args.dst}")
        if exists:
            try:
                st = args.dst.stat()
                logger.info(f"Dst stat: size={st.st_size}, mode={oct(st.st_mode)}")
            except Exception as ex:
                logger.warning(f"Dst stat failed: {ex}")
    except Exception as ex:
        logger.warning(f"Dst check failed: {ex}")

    # Retry loop for WinError 5 (access denied) — file may be locked briefly
    last_exc = None
    for attempt in range(3):
        try:
            os.replace(args.src, args.dst)
            logger.info(f"Replaced {args.dst}.")
            break
        except OSError as e:
            last_exc = e
            logger.warning(f"Replace attempt {attempt+1}/3 failed: {e}")
            # Try to make dst writable on access denied
            if getattr(e, "winerror", None) == 5:
                try:
                    if args.dst.exists():
                        os.chmod(args.dst, 0o777)
                        logger.info(f"chmod 777 on {args.dst}")
                except Exception as ce:
                    logger.warning(f"chmod failed: {ce}")
            if attempt < 2:
                time.sleep(0.7)
                continue
            logger.error(f"Failed to replace {args.dst}: {e}")
            return 3
    else:
        if last_exc is not None:
            logger.error(f"Failed to replace {args.dst}: {last_exc}")
            return 3

    if args.restart:
        _restart(args.dst, logger)

    logger.info("Updater finished successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())