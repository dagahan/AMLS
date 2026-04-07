from __future__ import annotations

import asyncio
from pathlib import Path
from time import perf_counter
from typing import Any
from typing import TYPE_CHECKING

from src.config.app_config import AppConfig
from src.config.business_config import BusinessConfig
from src.config.infra_config import InfraConfig
from src.config.loader import (
    build_business_hash,
    load_business_values,
    load_environment_values,
    load_infrastructure_values,
)
from src.config.validation import load_validators, validate_configuration
from src.core.logging import configure_logging, get_logger, is_logging_configured
from src.core.paths import find_project_root

if TYPE_CHECKING:
    from dynaconf import Validator


logger = get_logger(__name__)


class ConfigManager:
    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = (project_root or find_project_root()).resolve()
        self.env_path = self.project_root / ".env"
        self.business_path = self.project_root / "config/settings.toml"
        self.validators_path = self.project_root / "config/dynaconf_validators.toml"
        self._validators: list[Validator] = []
        self._infra_keys: set[str] = set()
        self._infra_values: dict[str, Any] | None = None
        self._environment_values: dict[str, str] | None = None
        self._app_config: AppConfig | None = None
        self._watcher_task: asyncio.Task[None] | None = None
        self._watcher_lock = asyncio.Lock()
        self._business_mtime_ns: int | None = None


    @property
    def app_config(self) -> AppConfig:
        if self._app_config is None:
            raise RuntimeError("Configuration manager is not initialized")
        return self._app_config


    def bootstrap(self) -> AppConfig:
        started_at = perf_counter()
        logger.info(
            "Loading application configuration",
            env_path=str(self.env_path),
            business_path=str(self.business_path),
            validators_path=str(self.validators_path),
        )

        env_values = load_environment_values(self.env_path)
        self._environment_values = dict(env_values)
        self._validators, self._infra_keys = load_validators(self.validators_path)
        infra_values = load_infrastructure_values(env_values, self._infra_keys)
        infra = InfraConfig(infra_values)
        self._infra_values = dict(infra_values)

        if not is_logging_configured():
            configure_logging(
                project_root=self.project_root,
                time_zone_name=infra.time_zone_name,
                level_name=infra.log_level_name,
                renderer_name=infra.log_renderer_name,
                access_logs=infra.access_logs_enabled,
            )

        business_values = load_business_values(self.business_path)
        validate_configuration(
            validators=self._validators,
            infra=infra_values,
            business=business_values,
        )

        self._app_config = self._build_app_config(
            infra=infra,
            business_values=business_values,
            environment_values=env_values,
        )
        self._business_mtime_ns = self._read_mtime_ns(self.business_path)

        logger.info(
            "Loaded application configuration",
            business_hash=self._app_config.business_hash,
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
        )
        return self._app_config


    async def start_watcher(self, interval_seconds: float = 1.0) -> None:
        if self._watcher_task is not None:
            logger.debug("Business config watcher is already running")
            return

        self._watcher_task = asyncio.create_task(
            self._watch_business_config(interval_seconds),
            name="config-settings-watcher",
        )
        logger.info(
            "Started business config watcher",
            business_path=str(self.business_path),
            interval_seconds=interval_seconds,
        )


    async def stop_watcher(self) -> None:
        if self._watcher_task is None:
            logger.debug("Business config watcher is not running")
            return

        self._watcher_task.cancel()
        try:
            await self._watcher_task
        except asyncio.CancelledError:
            pass
        finally:
            self._watcher_task = None
            logger.info("Stopped business config watcher", business_path=str(self.business_path))


    async def reload_business_config(self) -> AppConfig:
        async with self._watcher_lock:
            started_at = perf_counter()
            current_config = self.app_config
            infra_values = self._require_infra_values()
            business_values = load_business_values(self.business_path)
            validate_configuration(
                validators=self._validators,
                infra=infra_values,
                business=business_values,
                only=["business"],
            )
            previous_hash = current_config.business_hash
            self._app_config = self._build_app_config(
                infra=current_config.infra,
                business_values=business_values,
                environment_values=self._require_environment_values(),
            )
            self._business_mtime_ns = self._read_mtime_ns(self.business_path)
            logger.info(
                "Reloaded business configuration",
                business_path=str(self.business_path),
                previous_business_hash=previous_hash,
                current_business_hash=self._app_config.business_hash,
                duration_ms=round((perf_counter() - started_at) * 1000, 2),
            )
            return self._app_config


    async def _watch_business_config(self, interval_seconds: float) -> None:
        while True:
            await asyncio.sleep(interval_seconds)
            current_mtime_ns = self._read_mtime_ns(self.business_path)
            if current_mtime_ns is None or current_mtime_ns == self._business_mtime_ns:
                continue

            try:
                logger.info(
                    "Detected business configuration change",
                    business_path=str(self.business_path),
                    previous_mtime_ns=self._business_mtime_ns,
                    current_mtime_ns=current_mtime_ns,
                )
                await self.reload_business_config()
            except Exception as error:
                logger.error(
                    "Business configuration reload failed",
                    business_path=str(self.business_path),
                    error=str(error),
                )


    @staticmethod
    def _read_mtime_ns(path: Path) -> int | None:
        if not path.exists():
            return None
        return path.stat().st_mtime_ns


    def _build_app_config(
        self,
        *,
        infra: InfraConfig,
        business_values: dict[str, Any],
        environment_values: dict[str, str],
    ) -> AppConfig:
        business = BusinessConfig(business_values)
        return AppConfig(
            project_root=self.project_root,
            infra=infra,
            business=business,
            business_hash=build_business_hash(business_values),
            environment_values=environment_values,
        )


    def _require_infra_values(self) -> dict[str, Any]:
        if self._infra_values is None:
            raise RuntimeError("Infrastructure configuration is not initialized")
        return dict(self._infra_values)


    def _require_environment_values(self) -> dict[str, str]:
        if self._environment_values is None:
            raise RuntimeError("Environment configuration is not initialized")
        return dict(self._environment_values)


_CONFIG_MANAGER: ConfigManager | None = None


def bootstrap_config(project_root: Path | None = None) -> ConfigManager:
    global _CONFIG_MANAGER
    if _CONFIG_MANAGER is None:
        _CONFIG_MANAGER = ConfigManager(project_root=project_root)
        _CONFIG_MANAGER.bootstrap()
    return _CONFIG_MANAGER


def get_config_manager() -> ConfigManager:
    if _CONFIG_MANAGER is None:
        raise RuntimeError("Configuration manager is not initialized")
    return _CONFIG_MANAGER


def get_app_config() -> AppConfig:
    return get_config_manager().app_config
