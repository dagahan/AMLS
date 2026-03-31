from __future__ import annotations

import hashlib
import json
import os
import tomllib
from pathlib import Path
from typing import Any

from dotenv import dotenv_values


def load_environment_values(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        raise RuntimeError(f"Missing environment config file: {env_path}")

    raw_values = dotenv_values(env_path, encoding="utf-8")
    environment_values: dict[str, str] = {}

    for key, value in raw_values.items():
        if value is None:
            raise RuntimeError(f"Missing value for environment variable: {key}")
        environment_values[key] = value

    return environment_values


def load_infrastructure_values(
    env_values: dict[str, str],
    infra_keys: set[str],
) -> dict[str, Any]:
    infrastructure_values: dict[str, Any] = {}

    for infra_key in infra_keys:
        raw_value = env_values.get(infra_key)
        if raw_value is None:
            continue
        infrastructure_values[infra_key] = parse_scalar_value(raw_value)

    infrastructure_values["RUNNING_INSIDE_DOCKER"] = _load_running_inside_docker(env_values)
    return infrastructure_values


def load_business_values(business_path: Path) -> dict[str, Any]:
    if not business_path.exists():
        raise RuntimeError(f"Missing business config file: {business_path}")

    with business_path.open("rb") as business_file:
        raw_business = tomllib.load(business_file)

    if not isinstance(raw_business, dict):
        raise RuntimeError("Business config must be a TOML object")

    return raw_business


def build_business_hash(raw_business: dict[str, Any]) -> str:
    payload = json.dumps(raw_business, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def parse_scalar_value(raw_value: str) -> Any:
    normalized_value = raw_value.strip()

    try:
        parsed = tomllib.loads(f"value = {normalized_value}\n")
    except tomllib.TOMLDecodeError:
        return raw_value

    return parsed["value"]


def _load_running_inside_docker(env_values: dict[str, str]) -> Any:
    raw_file_value = env_values.get("RUNNING_INSIDE_DOCKER")
    if raw_file_value is not None:
        return parse_scalar_value(raw_file_value)

    raw_runtime_value = os.environ.get("RUNNING_INSIDE_DOCKER")
    if raw_runtime_value is None:
        return 0

    return parse_scalar_value(raw_runtime_value)
