from __future__ import annotations

import copy
import tomllib
from pathlib import Path
from typing import Any

from dynaconf import Dynaconf, Validator
from dynaconf.validator import ValidationError

from src.core.logging import get_logger


logger = get_logger(__name__)


def load_validators(path: Path) -> tuple[list[Validator], set[str]]:
    if not path.exists():
        raise RuntimeError(f"Missing config validator file: {path}")

    with path.open("rb") as validators_file:
        raw_validators = tomllib.load(validators_file)

    validators: list[Validator] = []
    infra_keys: set[str] = set()

    for key, rules in raw_validators.items():
        if not isinstance(rules, dict):
            raise RuntimeError(f"Validator rules for {key} must be a TOML object")

        validators.append(Validator(key, **rules))
        if not key.startswith("business."):
            infra_keys.add(key)

    return validators, infra_keys


def validate_configuration(
    *,
    validators: list[Validator],
    infra: dict[str, Any],
    business: dict[str, Any],
    only: list[str] | None = None,
) -> None:
    settings = Dynaconf(environments=False, merge_enabled=False)
    settings.validators.register(*validators)
    settings.update(infra, validate=False)
    settings.update({"business": copy.deepcopy(business)}, validate=False)

    try:
        settings.validators.validate_all(only=only)
    except ValidationError as error:
        logger.error(
            "Configuration validation failed",
            only=only,
            details=error.details or str(error),
        )
        raise RuntimeError(f"Configuration validation failed: {error}") from error
