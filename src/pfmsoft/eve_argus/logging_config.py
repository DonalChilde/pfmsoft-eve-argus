"""Logging configuration helpers for Eve Auth Manager.

Provides the default dictConfig-based logging setup used by the application,
including console output and rotating file handlers.

Notes:
    The logging configuration dictionary is intended to be customized in the
    handlers and loggers sections if the application needs different output
    destinations or verbosity.
"""

import logging
import logging.config
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def setup_logging(log_dir: Path) -> None:
    """Configure application logging handlers and formatters.

    Creates the target log directory when needed, then installs the default
    dictConfig-based logging setup for console and rotating file output.

    Args:
        log_dir: Directory where log files should be created.

    Notes:
        The configured root logger writes DEBUG-and-above messages to the info
        rotating file, WARNING-and-above messages to the warning rotating
        file, and CRITICAL-and-above messages to the console handler.
    """
    log_dir.mkdir(parents=True, exist_ok=True)

    # dictConfig replaces root handlers; keep deferred buffers so they can be
    # flushed after real handlers are installed.
    root_logger = logging.getLogger()
    deferred_handlers = [
        h for h in root_logger.handlers if isinstance(h, DeferredHandler)
    ]

    log_config: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "consoleFormatter": {
                "format": "%(asctime)s | %(name)s | %(levelname)s : %(message)s",
            },
            "fileFormatter": {
                "format": "%(asctime)s | %(name)s | %(levelname)-8s : %(message)s",
            },
            "brief": {
                "datefmt": "%H:%M:%S",
                "format": "%(levelname)-8s; %(name)s; %(message)s;",
            },
            "single-line": {
                "datefmt": "%H:%M:%S",
                "format": "%(levelname)-8s; %(asctime)s; %(name)s; %(module)s:%(funcName)s;%(lineno)d: %(message)s",
            },
            "multi-process": {
                "datefmt": "%H:%M:%S",
                "format": "%(levelname)-8s; [%(process)d]; %(name)s; %(module)s:%(funcName)s;%(lineno)d: %(message)s",
            },
            "multi-thread": {
                "datefmt": "%H:%M:%S",
                "format": "%(levelname)-8s; %(threadName)s; %(name)s; %(module)s:%(funcName)s;%(lineno)d: %(message)s",
            },
            "verbose": {
                "format": "%(levelname)-8s; [%(process)d]; %(threadName)s; %(name)s; %(module)s:%(funcName)s;%(lineno)d"
                ": %(message)s"
            },
            "multiline": {
                "format": "Level: %(levelname)s\nTime: %(asctime)s\nProcess: %(process)d\nThread: %(threadName)s\nLogger"
                ": %(name)s\nPath: %(module)s:%(lineno)d\nFunction :%(funcName)s\nMessage: %(message)s\n"
            },
            "mine": {
                "format": "%(asctime)s | %(levelname)-8s | %(funcName)s | %(message)s | [in %(pathname)s | %(lineno)d]"
            },
            "mine-multi": {
                "format": "%(asctime)s | %(levelname)-8s | %(funcName)s | [in %(pathname)s | %(lineno)d]\n\t %(message)s"
            },
        },
        "handlers": {
            "file": {
                "filename": log_dir / "debug.log",
                "level": "DEBUG",
                "class": "logging.FileHandler",
                "formatter": "mine",
            },
            "console": {
                "level": "CRITICAL",
                "class": "logging.StreamHandler",
                "formatter": "consoleFormatter",
            },
            "rot_file_info": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "mine-multi",
                "level": "INFO",
                "filename": log_dir / "rotating_info.log",
                "mode": "a",
                "encoding": "utf-8",
                "maxBytes": 10000000,
                "backupCount": 10,
            },
            "rot_file_warn": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "mine-multi",
                "level": "WARNING",
                "filename": log_dir / "rotating_warn.log",
                "mode": "a",
                "encoding": "utf-8",
                "maxBytes": 500000,
                "backupCount": 4,
            },
        },
        "loggers": {
            "": {
                "handlers": ["rot_file_info", "rot_file_warn", "console"],
                "level": "DEBUG",
            },
        },
    }
    logging.config.dictConfig(log_config)

    for deferred in deferred_handlers:
        if deferred not in root_logger.handlers:
            root_logger.addHandler(deferred)


class DeferredHandler(logging.Handler):
    """Buffers log records until real handlers are ready, then replays them."""

    def __init__(self, level: int = logging.NOTSET) -> None:
        """Initialize an in-memory record buffer."""
        super().__init__(level)
        self.buffer: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        """Store records until configured handlers are available."""
        self.buffer.append(record)

    def flush_to(self, handlers: list[logging.Handler]) -> None:
        """Replay buffered records through the given handlers, then clear."""
        for record in self.buffer:
            for handler in handlers:
                if record.levelno >= handler.level:
                    handler.handle(record)
        self.buffer.clear()


def init_deferred_handler() -> None:
    """Initialize a deferred handler for logging.

    This funtion sets up a deferred handler that can be used to buffer log messages in
    memory before they are flushed to the appropriate handlers.

    This is useful for capturing log messages emitted before the logging configuration
    is fully set up. The deferred handler will buffer these messages in memory and can
    be flushed to the appropriate handlers once they are configured.

    DeferredHandler is added to the root logger, and it captures all log messages at
    DEBUG level and above.

    It must be flushed to the appropriate handlers once they are configured to log the
    buffered messages.
    """
    root_logger = logging.getLogger()
    if any(isinstance(h, DeferredHandler) for h in root_logger.handlers):
        return
    root_logger.setLevel(logging.DEBUG)  # capture everything; filter at handler level
    deferred = DeferredHandler()
    root_logger.addHandler(deferred)


def flush_deferred_handler() -> None:
    """Replay buffered records into whatever handlers are currently configured.

    Call this after your real logging setup (dictConfig, basicConfig, manual
    addHandler calls, etc.) has run. Finds any DeferredHandler on the root
    logger, replays its buffer into all *other* handlers currently attached,
    then removes itself.

    Safe to call multiple times or when no DeferredHandler is present — it's
    a no-op in that case rather than an error.
    """
    root_logger = logging.getLogger()

    deferred_handlers = [
        h for h in root_logger.handlers if isinstance(h, DeferredHandler)
    ]
    if not deferred_handlers:
        return  # nothing to flush, or already finalized

    real_handlers = [
        h for h in root_logger.handlers if not isinstance(h, DeferredHandler)
    ]

    for deferred in deferred_handlers:
        deferred.flush_to(real_handlers)
        root_logger.removeHandler(deferred)
