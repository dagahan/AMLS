from __future__ import annotations

from functools import lru_cache
from typing import Any

from valkey import Valkey

from src.core.utils import EnvTools


@lru_cache(maxsize=1)
def get_valkey_client() -> Any:
    return Valkey(
        host=EnvTools.get_service_host("valkey"),
        port=int(EnvTools.get_service_port("valkey")),
        decode_responses=True,
    )
