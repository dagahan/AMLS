import inspect
import logging
import sys

from loguru import logger

from src.core.utils import EnvTools, FileSystemTools


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            log_level = logger.level(record.levelname).name
        except ValueError:
            log_level = record.levelname

        current_frame = inspect.currentframe()
        depth = 0
        while current_frame is not None and current_frame.f_code.co_filename == logging.__file__:
            current_frame = current_frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(log_level, record.getMessage())


class LogSetup:
    @staticmethod
    def configure() -> None:
        FileSystemTools.ensure_directory_exists("debug")
        EnvTools.set_env_var("TZ", EnvTools.load_env_var("TZ") or "UTC")

        logger.remove()
        logger.add(
            sys.stdout,
            format=(
                "<green>{time:HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
                "{message}"
            ),
            level="DEBUG",
            catch=True,
        )
        logger.add(
            "debug/debug.json",
            format="{time} {level} {message}",
            serialize=True,
            rotation="1 day",
            retention="14 days",
            compression="zip",
            level="DEBUG",
            catch=True,
        )

