from __future__ import annotations

import logging
import os
import sys
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import structlog
from structlog.contextvars import merge_contextvars
from structlog.dev import ConsoleRenderer, set_exc_info
from structlog.processors import JSONRenderer, StackInfoRenderer, TimeStamper
from structlog.stdlib import (
    LoggerFactory,
    ProcessorFormatter,
    add_log_level,
    add_logger_name,
)

from src.core.paths import find_project_root

if TYPE_CHECKING:
    from structlog.typing import Processor


def configure_logging(
    *,
    project_root: Path | None,
    time_zone_name: str,
    level_name: str,
    renderer_name: str,
    access_logs: bool,
) -> None:
    resolved_project_root = (project_root or find_project_root()).resolve()
    _configure_time_zone(time_zone_name)

    level = _resolve_log_level(level_name)
    renderer = _resolve_renderer_kind(renderer_name)
    debug_file_path = resolved_project_root / "backend" / "debug" / "debug.json"
    debug_file_path.parent.mkdir(parents=True, exist_ok=True)

    shared_processors = _build_shared_processors()
    console_handler = _build_console_handler(level, renderer, shared_processors)
    json_handler = _build_json_handler(level, debug_file_path, shared_processors)
    root_logger = logging.getLogger()

    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        handler.close()

    root_logger.setLevel(level)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(json_handler)

    _configure_named_loggers(level, access_logs)
    structlog.configure(
        processors=[*shared_processors, ProcessorFormatter.wrap_for_formatter],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def is_logging_configured() -> bool:
    return structlog.is_configured()


def _configure_time_zone(time_zone_name: str) -> None:
    os.environ["TZ"] = time_zone_name
    if hasattr(time, "tzset"):
        time.tzset()


def _build_shared_processors() -> tuple[Processor, ...]:
    return (
        merge_contextvars,
        add_logger_name,
        add_log_level,
        StackInfoRenderer(),
        set_exc_info,
        TimeStamper(fmt="iso", utc=False),
    )


def _build_console_handler(
    level: int,
    renderer: Literal["console", "json"],
    shared_processors: tuple[Processor, ...],
) -> logging.Handler:
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(
        ProcessorFormatter(
            foreign_pre_chain=list(shared_processors),
            processors=[
                ProcessorFormatter.remove_processors_meta,
                _build_console_renderer(renderer),
            ],
        )
    )
    return console_handler


def _build_json_handler(
    level: int,
    debug_file_path: Path,
    shared_processors: tuple[Processor, ...],
) -> logging.Handler:
    json_handler = TimedRotatingFileHandler(
        filename=debug_file_path,
        when="midnight",
        backupCount=14,
        encoding="utf-8",
    )
    json_handler.setLevel(level)
    json_handler.setFormatter(
        ProcessorFormatter(
            foreign_pre_chain=list(shared_processors),
            processors=[
                ProcessorFormatter.remove_processors_meta,
                JSONRenderer(),
            ],
        )
    )
    return json_handler


def _build_console_renderer(renderer: Literal["console", "json"]) -> Processor:
    if renderer == "json":
        return JSONRenderer()

    force_colors = bool(os.getenv("FORCE_COLOR"))
    disable_colors = bool(os.getenv("NO_COLOR"))

    return ConsoleRenderer(
        colors=(force_colors or sys.stdout.isatty()) and not disable_colors,
    )


def _configure_named_loggers(level: int, access_logs: bool) -> None:
    logger_names = (
        "uvicorn",
        "uvicorn.error",
        "sqlalchemy.engine",
        "asyncio",
    )

    for logger_name in logger_names:
        named_logger = logging.getLogger(logger_name)
        named_logger.handlers.clear()
        named_logger.setLevel(level)
        named_logger.propagate = True

    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.setLevel(level)
    access_logger.propagate = access_logs


def _resolve_log_level(level_name: str) -> int:
    normalized_name = level_name.strip().upper()
    level = getattr(logging, normalized_name, None)
    if isinstance(level, int):
        return level
    raise RuntimeError(f"Unsupported log level: {level_name}")


def _resolve_renderer_kind(renderer_name: str) -> Literal["console", "json"]:
    normalized_name = renderer_name.strip().lower()
    if normalized_name == "console":
        return "console"
    if normalized_name == "json":
        return "json"
    raise RuntimeError(f"Unsupported log renderer: {renderer_name}")
