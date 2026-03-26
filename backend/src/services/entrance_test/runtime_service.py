from __future__ import annotations

import uuid

from loguru import logger
import numpy as np

from src.models.pydantic import EntranceTestRuntimePayload, RuntimeSnapshot
from src.storage.storage_manager import StorageManager


class EntranceTestRuntimeService:
    runtime_kind = "exact_forest_bayes_v2"


    def __init__(self, storage_manager: StorageManager) -> None:
        self.storage_manager = storage_manager


    async def load_runtime_payload(
        self,
        entrance_test_session_id: uuid.UUID,
    ) -> EntranceTestRuntimePayload | None:
        runtime_payload = await self.storage_manager.get_entrance_test_runtime_storage().get_runtime_payload(
            entrance_test_session_id
        )
        if runtime_payload is None:
            return None

        if runtime_payload.runtime_kind != self.runtime_kind:
            logger.warning(
                "Entrance test runtime payload kind is stale and will be ignored: session_id={}, runtime_kind={}",
                entrance_test_session_id,
                runtime_payload.runtime_kind,
            )
            await self.storage_manager.get_entrance_test_runtime_storage().delete_runtime_payload(
                entrance_test_session_id
            )
            return None

        return runtime_payload


    async def load_runtime_snapshot(
        self,
        entrance_test_session_id: uuid.UUID,
    ) -> RuntimeSnapshot | None:
        runtime_payload = await self.load_runtime_payload(entrance_test_session_id)
        if runtime_payload is None:
            return None

        return self.build_runtime_snapshot(runtime_payload)


    async def save_runtime_snapshot(
        self,
        entrance_test_session_id: uuid.UUID,
        structure_version: int,
        runtime_snapshot: RuntimeSnapshot,
    ) -> EntranceTestRuntimePayload:
        runtime_payload = self.build_runtime_payload(
            structure_version=structure_version,
            runtime_snapshot=runtime_snapshot,
        )
        await self.storage_manager.get_entrance_test_runtime_storage().set_runtime_payload(
            entrance_test_session_id,
            runtime_payload,
        )
        return runtime_payload


    async def delete_runtime_snapshot(
        self,
        entrance_test_session_id: uuid.UUID,
    ) -> None:
        await self.storage_manager.get_entrance_test_runtime_storage().delete_runtime_payload(
            entrance_test_session_id
        )


    def build_runtime_payload(
        self,
        structure_version: int,
        runtime_snapshot: RuntimeSnapshot,
    ) -> EntranceTestRuntimePayload:
        return EntranceTestRuntimePayload(
            runtime_kind=self.runtime_kind,
            node_scores=runtime_snapshot.node_scores.astype(np.float64).tolist(),
            marginal_probabilities=runtime_snapshot.marginal_probabilities.astype(
                np.float64
            ).tolist(),
            initial_entropy=runtime_snapshot.initial_entropy,
            current_entropy=runtime_snapshot.current_entropy,
            current_temperature=runtime_snapshot.current_temperature,
            asked_problem_type_indices=list(runtime_snapshot.asked_problem_type_indices),
            leader_state_index=runtime_snapshot.leader_state_index,
            leader_state_probability=runtime_snapshot.leader_state_probability,
            leader_problem_type_indices=list(runtime_snapshot.leader_problem_type_indices),
            structure_version=structure_version,
        )


    @staticmethod
    def build_runtime_snapshot(
        runtime_payload: EntranceTestRuntimePayload,
    ) -> RuntimeSnapshot:
        logger.debug(
            "Building forest runtime snapshot from payload: structure_version={}, node_count={}, asked_count={}",
            runtime_payload.structure_version,
            len(runtime_payload.node_scores),
            len(runtime_payload.asked_problem_type_indices),
        )
        return RuntimeSnapshot(
            node_scores=np.asarray(runtime_payload.node_scores, dtype=np.float64),
            marginal_probabilities=np.asarray(
                runtime_payload.marginal_probabilities,
                dtype=np.float64,
            ),
            initial_entropy=runtime_payload.initial_entropy,
            current_entropy=runtime_payload.current_entropy,
            current_temperature=runtime_payload.current_temperature,
            asked_problem_type_indices=tuple(runtime_payload.asked_problem_type_indices),
            leader_state_index=runtime_payload.leader_state_index,
            leader_state_probability=runtime_payload.leader_state_probability,
            leader_problem_type_indices=tuple(
                runtime_payload.leader_problem_type_indices
            ),
        )
