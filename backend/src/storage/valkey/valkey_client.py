from __future__ import annotations

import asyncio
from functools import lru_cache
from weakref import WeakKeyDictionary

from valkey import Valkey
from valkey.asyncio import Valkey as AsyncValkey

from src.config import AppConfig, get_app_config

_ASYNC_VALKEY_CLIENTS: WeakKeyDictionary[asyncio.AbstractEventLoop, AsyncValkey] = WeakKeyDictionary()


@lru_cache(maxsize=1)
def get_valkey_client() -> Valkey:
    app_config = get_app_config()
    return _build_sync_valkey_client(app_config)


def get_async_valkey_client() -> AsyncValkey:
    loop = asyncio.get_running_loop()
    client = _ASYNC_VALKEY_CLIENTS.get(loop)
    if client is None:
        app_config = get_app_config()
        client = _build_async_valkey_client(app_config)
        _ASYNC_VALKEY_CLIENTS[loop] = client

    return client


def _build_sync_valkey_client(app_config: AppConfig) -> Valkey:
    return Valkey(
        host=app_config.valkey_host(),
        port=app_config.infra.valkey_port,
        decode_responses=True,
    )


def _build_async_valkey_client(app_config: AppConfig) -> AsyncValkey:
    return AsyncValkey(
        host=app_config.valkey_host(),
        port=app_config.infra.valkey_port,
        decode_responses=True,
    )
