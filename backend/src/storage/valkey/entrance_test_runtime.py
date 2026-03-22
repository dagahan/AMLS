from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from loguru import logger

from src.models.pydantic import EntranceTestRuntimePayload

if TYPE_CHECKING:
    from collections.abc import Callable

    from valkey.asyncio import Valkey as AsyncValkey


class EntranceTestRuntimeStorage:
    def __init__(
        self,
        valkey_client_factory: Callable[[], AsyncValkey],
    ) -> None:
        self.valkey_client_factory = valkey_client_factory


    def _get_client(self) -> AsyncValkey:
        return self.valkey_client_factory()


    async def get_runtime_payload(
        self,
        entrance_test_session_id: uuid.UUID,
    ) -> EntranceTestRuntimePayload | None:
        runtime_json = await self._get_client().get(
            self._build_runtime_key(entrance_test_session_id)
        )
        if runtime_json is None:
            logger.info(
                "Entrance test runtime cache miss: session_id={}",
                entrance_test_session_id,
            )
            return None

        logger.info(
            "Entrance test runtime cache hit: session_id={}",
            entrance_test_session_id,
        )
        try:
            return EntranceTestRuntimePayload.model_validate_json(runtime_json)
        except Exception as error:
            logger.warning(
                "Entrance test runtime payload is incompatible and will be ignored: session_id={}, error={}",
                entrance_test_session_id,
                error,
            )
            await self.delete_runtime_payload(entrance_test_session_id)
            return None


    async def set_runtime_payload(
        self,
        entrance_test_session_id: uuid.UUID,
        runtime_payload: EntranceTestRuntimePayload,
    ) -> None:
        await self._get_client().set(
            self._build_runtime_key(entrance_test_session_id),
            runtime_payload.model_dump_json(),
        )
        logger.info(
            "Stored entrance test runtime payload: session_id={}, structure_version={}, runtime_kind={}, node_count={}",
            entrance_test_session_id,
            runtime_payload.structure_version,
            runtime_payload.runtime_kind,
            len(runtime_payload.node_scores),
        )


    async def delete_runtime_payload(
        self,
        entrance_test_session_id: uuid.UUID,
    ) -> None:
        await self._get_client().delete(self._build_runtime_key(entrance_test_session_id))
        logger.info(
            "Deleted entrance test runtime payload: session_id={}",
            entrance_test_session_id,
        )


    @staticmethod
    def _build_runtime_key(entrance_test_session_id: uuid.UUID) -> str:
        return f"EntranceTestRuntime:{entrance_test_session_id}"
