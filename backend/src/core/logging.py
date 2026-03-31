from __future__ import annotations

from typing import Any

from structlog.contextvars import bind_contextvars, clear_contextvars, get_contextvars
from structlog.stdlib import (
    BoundLogger,
    get_logger as get_structlog_logger,
)

from src.core.logging_runtime import configure_logging, is_logging_configured

__all__ = [
    "AppLogger",
    "bind_context",
    "clear_context",
    "configure_logging",
    "get_context",
    "get_logger",
    "is_logging_configured",
]


class AppLogger:
    def __init__(self, logger: BoundLogger) -> None:
        self._logger = logger


    def bind(self, **fields: object) -> AppLogger:
        return AppLogger(self._logger.bind(**fields))


    def debug(self, event: str, *args: object, **fields: object) -> None:
        self._logger.debug(_format_event_message(event, args), **fields)


    def info(self, event: str, *args: object, **fields: object) -> None:
        self._logger.info(_format_event_message(event, args), **fields)


    def warning(self, event: str, *args: object, **fields: object) -> None:
        self._logger.warning(_format_event_message(event, args), **fields)


    def error(self, event: str, *args: object, **fields: object) -> None:
        self._logger.error(_format_event_message(event, args), **fields)


    def critical(self, event: str, *args: object, **fields: object) -> None:
        self._logger.critical(_format_event_message(event, args), **fields)


    def exception(self, event: str, *args: object, **fields: object) -> None:
        self._logger.exception(_format_event_message(event, args), **fields)


def bind_context(**fields: object) -> None:
    bind_contextvars(**fields)


def clear_context() -> None:
    clear_contextvars()


def get_context() -> dict[str, Any]:
    return dict(get_contextvars())


def get_logger(name: str | None = None) -> AppLogger:
    return AppLogger(get_structlog_logger(name))


def _format_event_message(event: str, args: tuple[object, ...]) -> str:
    if not args:
        return event

    try:
        return event.format(*args)
    except Exception as error:
        return f"{event} | formatting_error={error!r} | args={args!r}"
