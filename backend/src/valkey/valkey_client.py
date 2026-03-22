from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any
from weakref import WeakKeyDictionary

from valkey import Valkey
from valkey.asyncio import Valkey as AsyncValkey

from src.config import get_app_config

_ASYNC_VALKEY_CLIENTS: WeakKeyDictionary[asyncio.AbstractEventLoop, AsyncValkey] = WeakKeyDictionary()


@lru_cache(maxsize=1)
def get_valkey_client() -> Any:
    app_config = get_app_config()
    return Valkey(
        host=app_config.service_host("valkey"),
        port=app_config.service_port("valkey"),
        decode_responses=True,
    )


def get_async_valkey_client() -> AsyncValkey:
    loop = asyncio.get_running_loop()
    client = _ASYNC_VALKEY_CLIENTS.get(loop)
    if client is None:
        app_config = get_app_config()
        client = AsyncValkey(
            host=app_config.service_host("valkey"),
            port=app_config.service_port("valkey"),
            decode_responses=True,
        )
        _ASYNC_VALKEY_CLIENTS[loop] = client

    return client
