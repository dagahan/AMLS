from __future__ import annotations

import tomllib
from typing import Any, ClassVar

from loguru import logger


class ConfigLoader:
    __instance: ClassVar["ConfigLoader | None"] = None
    __config: ClassVar[dict[str, Any]] = {}


    def __new__(cls) -> "ConfigLoader":
        if cls.__instance is None:
            cls.__instance = super().__new__(cls)
            cls._load()
        return cls.__instance


    @classmethod
    def _load(cls) -> None:
        try:
            with open("pyproject.toml", "rb") as file_pointer:
                cls.__config = tomllib.load(file_pointer)
        except Exception as error:
            logger.critical(f"Config load failed: {error}")
            raise


    @classmethod
    def get(cls, section: str, key: str = "") -> Any:
        if key == "":
            return cls.__config.get(section, {})
        return cls.__config[section][key]


    def __getitem__(self, section: str) -> Any:
        return type(self).get(section)
