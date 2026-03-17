from typing import Any

from valkey import Valkey

from src.core.utils import EnvTools


class ValkeyService:
    def __init__(self) -> None:
        self.valkey: Any = Valkey(
            host=EnvTools.get_service_host("valkey"),
            port=int(EnvTools.get_service_port("valkey")),
            decode_responses=True,
        )
