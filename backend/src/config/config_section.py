from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any, cast


class ConfigSection:
    __slots__ = ("_values",)

    def __init__(self, values: Mapping[str, Any]) -> None:
        self._values: dict[str, Any] = dict(values)


    def _require_string(self, key: str) -> str:
        return self._read_string(self._values, key, key)


    def _require_integer(self, key: str) -> int:
        return self._read_integer(self._values, key, key)


    def _require_float(self, key: str) -> float:
        return self._read_float(self._values, key, key)


    def _require_flag(self, key: str) -> bool:
        return self._read_flag(self._values, key, key)


    def _require_mapping(self, key: str) -> dict[str, Any]:
        return self._read_mapping(self._values, key, key)


    def _snapshot(self) -> dict[str, object]:
        return cast("dict[str, object]", deepcopy(self._values))


    @staticmethod
    def _read_string(values: Mapping[str, Any], key: str, location: str) -> str:
        value = ConfigSection._read_value(values, key, location)
        if not isinstance(value, str):
            raise RuntimeError(f"Expected {location} to be a string")
        return value


    @staticmethod
    def _read_integer(values: Mapping[str, Any], key: str, location: str) -> int:
        value = ConfigSection._read_value(values, key, location)
        if isinstance(value, bool) or not isinstance(value, int):
            raise RuntimeError(f"Expected {location} to be an integer")
        return value


    @staticmethod
    def _read_float(values: Mapping[str, Any], key: str, location: str) -> float:
        value = ConfigSection._read_value(values, key, location)
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise RuntimeError(f"Expected {location} to be a number")
        return float(value)


    @staticmethod
    def _read_flag(values: Mapping[str, Any], key: str, location: str) -> bool:
        value = ConfigSection._read_value(values, key, location)
        if isinstance(value, bool):
            return value
        if value in {0, 1}:
            return bool(value)
        raise RuntimeError(f"Expected {location} to be a boolean flag")


    @staticmethod
    def _read_mapping(values: Mapping[str, Any], key: str, location: str) -> dict[str, Any]:
        value = ConfigSection._read_value(values, key, location)
        if not isinstance(value, dict):
            raise RuntimeError(f"Expected {location} to be a mapping")
        return value


    @staticmethod
    def _read_value(values: Mapping[str, Any], key: str, location: str) -> object:
        if key not in values:
            raise RuntimeError(f"Missing config value: {location}")
        return values[key]
