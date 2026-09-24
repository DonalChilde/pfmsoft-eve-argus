"""Helpers for logging execution timing."""

import functools
import logging
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


def log_timing(
    *,
    logger: logging.Logger,
    level: int = logging.DEBUG,
    label: str | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Log function execution time when the logger level is enabled."""

    def decorator(function: Callable[P, R]) -> Callable[P, R]:
        timer_label = label or f"{function.__module__}.{function.__qualname__}"

        @functools.wraps(function)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            if not logger.isEnabledFor(level):
                return function(*args, **kwargs)

            started_at = time.perf_counter_ns()
            try:
                return function(*args, **kwargs)
            finally:
                # Calculate the elapsed time in seconds
                elapsed_s = (time.perf_counter_ns() - started_at) / 1_000_000_000
                logger.log(
                    level,
                    "timing label=%s elapsed=%.6f seconds",
                    timer_label,
                    elapsed_s,
                )

        return wrapper

    return decorator


@contextmanager
def log_timing_block(
    *,
    logger: logging.Logger,
    label: str,
    level: int = logging.DEBUG,
) -> Generator[None]:
    """Log block execution time when the logger level is enabled."""
    if not logger.isEnabledFor(level):
        yield
        return

    started_at = time.perf_counter_ns()
    try:
        yield
    finally:
        elapsed_s = (time.perf_counter_ns() - started_at) / 1_000_000_000
        logger.log(
            level,
            "timing label=%s elapsed=%.6f seconds",
            label,
            elapsed_s,
        )
