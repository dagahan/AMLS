from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any
from weakref import WeakKeyDictionary

from valkey import Valkey
from valkey.asyncio import Valkey as AsyncValkey

from src.core.utils import EnvTools

_ASYNC_VALKEY_CLIENTS: WeakKeyDictionary[asyncio.AbstractEventLoop, AsyncValkey] = WeakKeyDictionary()


@lru_cache(maxsize=1)
def get_valkey_client() -> Any:
    return Valkey(
        host=EnvTools.get_service_host("valkey"),
        port=int(EnvTools.get_service_port("valkey")),
        decode_responses=True,
    )


def get_async_valkey_client() -> AsyncValkey:
    loop = asyncio.get_running_loop()
    client = _ASYNC_VALKEY_CLIENTS.get(loop)
    if client is None:
        client = AsyncValkey(
            host=EnvTools.get_service_host("valkey"),
            port=int(EnvTools.get_service_port("valkey")),
            decode_responses=True,
        )
        _ASYNC_VALKEY_CLIENTS[loop] = client

    return client
