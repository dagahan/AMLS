from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any
import tomllib

from dynaconf import Dynaconf, Validator
from dynaconf.validator import ValidationError
from dotenv import dotenv_values, load_dotenv
from loguru import logger

from src.core.paths import find_project_root, resolve_project_path

DEFAULT_INFRA_KEYS = {"RUNNING_INSIDE_DOCKER"}


class ConfigSection(Mapping[str, Any]):
    def __init__(self, data: Mapping[str, Any]) -> None:
        self._data = copy.deepcopy(dict(data))


    def __getitem__(self, key: str) -> Any:
        return self._data[key]


    def __iter__(self) -> Iterator[str]:
        return iter(self._data)


    def __len__(self) -> int:
        return len(self._data)


    def get(self, path: str, default: Any = None) -> Any:
        if path == "":
            return self.as_dict()

        current: Any = self._data
        for part in path.split("."):
            if not isinstance(current, Mapping) or part not in current:
                return default
            current = current[part]
        return current


    def require(self, path: str) -> Any:
        value = self.get(path)
        if value is None:
            raise RuntimeError(f"Missing configuration value: {path}")
        return value


    def as_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self._data)


class AppConfig:
    def __init__(
        self,
        *,
        project_root: Path,
        infra: Mapping[str, Any],
        business: Mapping[str, Any],
        business_hash: str,
    ) -> None:
        self.project_root = project_root
        self.infra = ConfigSection(infra)
        self.business = ConfigSection(business)
        self.business_hash = business_hash


    def get(self, path: str, default: Any = None) -> Any:
        if path.startswith("infra."):
            return self.infra.get(path.removeprefix("infra."), default)
        if path.startswith("business."):
            return self.business.get(path.removeprefix("business."), default)
        return default


    def is_running_inside_docker(self) -> bool:
        return bool(int(self.infra.get("RUNNING_INSIDE_DOCKER", 0)))


    def service_host(self, service_name: str) -> str:
        if self.is_running_inside_docker():
            project_name = str(self.infra.require("COMPOSE_PROJECT_NAME"))
            return f"{service_name}-{project_name}"
        return str(self.infra.require(f"{service_name.upper()}_HOST"))


    def service_port(self, service_name: str) -> int:
        return int(self.infra.require(f"{service_name.upper()}_PORT"))


    def resolve_path(self, path_value: str) -> Path:
        return resolve_project_path(path_value, self.project_root)


    def business_snapshot(self) -> dict[str, Any]:
        return self.business.as_dict()


    def get_difficulty(self, difficulty_key: str) -> dict[str, Any]:
        difficulty = self.business.get(f"difficulties.{difficulty_key}")
        if not isinstance(difficulty, dict):
            raise RuntimeError(f"Unknown configured difficulty: {difficulty_key}")
        return copy.deepcopy(difficulty)


    def list_difficulties(self) -> list[dict[str, Any]]:
        difficulties = self.business.get("difficulties", {})
        if not isinstance(difficulties, Mapping):
            return []
        return [
            {"key": key, **copy.deepcopy(value)}
            for key, value in difficulties.items()
            if isinstance(value, Mapping)
        ]


class ConfigManager:
    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = (project_root or find_project_root()).resolve()
        self.env_path = self.project_root / ".env"
        self.business_path = self.project_root / "config/settings.toml"
        self.validators_path = self.project_root / "config/dynaconf_validators.toml"
        self._validators: list[Validator] = []
        self._infra_keys: set[str] = set(DEFAULT_INFRA_KEYS)
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
        if self.env_path.exists():
            load_dotenv(self.env_path, override=True, interpolate=True, encoding="utf-8")

        self._validators, self._infra_keys = self._load_validators(self.validators_path)
        infra = self._load_infra()
        business = self._load_business()
        self._validate(infra=infra, business=business)

        business_hash = self._build_business_hash(business)
        self._app_config = AppConfig(
            project_root=self.project_root,
            infra=infra,
            business=business,
            business_hash=business_hash,
        )
        self._business_mtime_ns = self._read_mtime_ns(self.business_path)

        logger.info(
            "Loaded application configuration: env_path={}, business_path={}, validators_path={}, business_hash={}",
            self.env_path,
            self.business_path,
            self.validators_path,
            business_hash,
        )
        return self._app_config


    async def start_watcher(self, interval_seconds: float = 1.0) -> None:
        if self._watcher_task is not None:
            return

        self._watcher_task = asyncio.create_task(
            self._watch_business_config(interval_seconds),
            name="config-settings-watcher",
        )
        logger.info("Started business config watcher for {}", self.business_path)


    async def stop_watcher(self) -> None:
        if self._watcher_task is None:
            return

        self._watcher_task.cancel()
        try:
            await self._watcher_task
        except asyncio.CancelledError:
            pass
        finally:
            self._watcher_task = None
            logger.info("Stopped business config watcher for {}", self.business_path)


    async def reload_business_config(self) -> AppConfig:
        async with self._watcher_lock:
            current_config = self.app_config
            business = self._load_business()
            self._validate(infra=current_config.infra.as_dict(), business=business, only=["business"])
            business_hash = self._build_business_hash(business)
            self._app_config = AppConfig(
                project_root=self.project_root,
                infra=current_config.infra.as_dict(),
                business=business,
                business_hash=business_hash,
            )
            self._business_mtime_ns = self._read_mtime_ns(self.business_path)
            logger.info(
                "Reloaded business configuration: business_path={}, business_hash={}",
                self.business_path,
                business_hash,
            )
            return self._app_config


    def _load_infra(self) -> dict[str, Any]:
        file_values = {
            key: value
            for key, value in dotenv_values(self.env_path).items()
            if value is not None
        } if self.env_path.exists() else {}

        data: dict[str, Any] = {}
        for key in self._infra_keys:
            raw_value = file_values.get(key)
            if raw_value is None:
                raw_value = os.environ.get(key)
            if raw_value is None:
                continue
            data[key] = self._parse_scalar(raw_value)

        if "RUNNING_INSIDE_DOCKER" not in data:
            raw_running_inside_docker = os.environ.get("RUNNING_INSIDE_DOCKER")
            data["RUNNING_INSIDE_DOCKER"] = (
                self._parse_scalar(raw_running_inside_docker)
                if raw_running_inside_docker is not None
                else 0
            )

        return data


    def _load_business(self) -> dict[str, Any]:
        if not self.business_path.exists():
            raise RuntimeError(f"Missing business config file: {self.business_path}")

        with self.business_path.open("rb") as config_file:
            raw_business = tomllib.load(config_file)

        if not isinstance(raw_business, dict):
            raise RuntimeError("Business config must be a TOML object")
        return raw_business


    def _validate(
        self,
        *,
        infra: Mapping[str, Any],
        business: Mapping[str, Any],
        only: list[str] | None = None,
    ) -> None:
        settings = Dynaconf(environments=False, merge_enabled=False)
        settings.validators.register(*self._validators)
        settings.update(dict(infra), validate=False)
        settings.update({"business": copy.deepcopy(dict(business))}, validate=False)

        try:
            settings.validators.validate_all(only=only)
        except ValidationError as error:
            logger.error(
                "Configuration validation failed: only={}, details={}",
                only,
                error.details or str(error),
            )
            raise RuntimeError(f"Configuration validation failed: {error}") from error


    async def _watch_business_config(self, interval_seconds: float) -> None:
        while True:
            await asyncio.sleep(interval_seconds)
            current_mtime_ns = self._read_mtime_ns(self.business_path)
            if current_mtime_ns is None or current_mtime_ns == self._business_mtime_ns:
                continue

            try:
                await self.reload_business_config()
            except Exception as error:
                logger.error(
                    "Business configuration reload failed for {}: {}. Previous config kept.",
                    self.business_path,
                    error,
                )


    @staticmethod
    def _read_mtime_ns(path: Path) -> int | None:
        if not path.exists():
            return None
        return path.stat().st_mtime_ns


    @staticmethod
    def _build_business_hash(business: Mapping[str, Any]) -> str:
        payload = json.dumps(business, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


    @staticmethod
    def _parse_scalar(raw_value: str) -> Any:
        normalized_value = raw_value.strip()
        try:
            parsed = tomllib.loads(f"value = {normalized_value}\n")
        except tomllib.TOMLDecodeError:
            return raw_value
        return parsed["value"]


    @staticmethod
    def _load_validators(path: Path) -> tuple[list[Validator], set[str]]:
        if not path.exists():
            raise RuntimeError(f"Missing config validator file: {path}")

        with path.open("rb") as validators_file:
            raw_validators = tomllib.load(validators_file)

        validators: list[Validator] = []
        infra_keys: set[str] = set(DEFAULT_INFRA_KEYS)
        for key, rules in raw_validators.items():
            if not isinstance(rules, dict):
                raise RuntimeError(f"Validator rules for {key} must be a TOML object")
            validators.append(Validator(key, **rules))
            if not key.startswith("business."):
                infra_keys.add(key)
        return validators, infra_keys


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
