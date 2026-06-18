"""File logging for deploy services — full app logs + error traces under .run/logs/."""

from __future__ import annotations

import asyncio
import faulthandler
import logging
import os
import signal
import sys
from pathlib import Path

_LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"


def setup_service_logging(service: str, deploy_root: Path, *, level: int = logging.INFO) -> Path:
    log_dir = deploy_root / ".run" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    main_log = log_dir / f"{service}.log"
    err_log = log_dir / f"{service}.err.log"

    formatter = logging.Formatter(_LOG_FORMAT)
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    main_handler = logging.FileHandler(main_log, encoding="utf-8")
    main_handler.setFormatter(formatter)
    root.addHandler(main_handler)

    err_handler = logging.FileHandler(err_log, encoding="utf-8")
    err_handler.setLevel(logging.ERROR)
    err_handler.setFormatter(formatter)
    root.addHandler(err_handler)

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)
    root.addHandler(console)

    crash_log = log_dir / "faulthandler.log"
    faulthandler.enable(open(crash_log, "a", encoding="utf-8"), all_threads=True)

    def _unhandled(exc_type, exc, tb) -> None:
        logging.getLogger(f"minimal.{service}.crash").critical(
            "Unhandled exception",
            exc_info=(exc_type, exc, tb),
        )
        from failure_watchdog import capture

        capture(
            "unhandled_exception",
            {
                "exc_type": getattr(exc_type, "__name__", str(exc_type)),
                "error": str(exc),
            },
        )
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _unhandled

    logging.getLogger(f"minimal.{service}").info(
        "Logging initialized service=%s main=%s err=%s",
        service,
        main_log,
        err_log,
    )
    return main_log


def install_asyncio_exception_handler(service: str) -> None:
    loop = asyncio.get_running_loop()

    def _asyncio_handler(_loop: asyncio.AbstractEventLoop, context: dict) -> None:
        exc = context.get("exception")
        msg = context.get("message", "asyncio error")
        logging.getLogger(f"minimal.{service}.asyncio").error(
            "Asyncio: %s",
            msg,
            exc_info=exc if isinstance(exc, BaseException) else None,
        )
        from failure_watchdog import capture

        capture(
            "asyncio_error",
            {
                "message": msg,
                "error": str(exc) if isinstance(exc, BaseException) else "",
            },
        )

    loop.set_exception_handler(_asyncio_handler)


def install_signal_logging(service: str) -> None:
    """Log termination signals so Mac kills/suspends show up in agent.log."""
    log = logging.getLogger(f"minimal.{service}")

    def _handler(signum: int, _frame) -> None:
        name = signal.Signals(signum).name
        log.warning(
            "Received signal %s (%s) pid=%s ppid=%s",
            name,
            signum,
            os.getpid(),
            os.getppid(),
        )
        from failure_watchdog import capture

        if signum == signal.SIGHUP:
            capture(
                "signal",
                {
                    "signal": name,
                    "signum": signum,
                    "ppid": os.getppid(),
                },
            )
        if signum in (signal.SIGTERM, signal.SIGINT):
            raise SystemExit(128 + signum)

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, _handler)
    log.info("Signal logging enabled pid=%s ppid=%s", os.getpid(), os.getppid())
