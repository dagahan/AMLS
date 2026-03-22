from __future__ import annotations

import gzip
import uuid
from typing import TYPE_CHECKING

from loguru import logger
import numpy as np
from sqlalchemy import select

from src.core.utils import EnvTools, StringTools
from src.db.enums import EntranceTestStructureStatus
from src.math_models.entrance_assessment import (
    ForestStructureError,
    build_forest_artifact,
    build_graph_artifact,
)
from src.math_models.entrance_assessment.types import ForestArtifact, GraphArtifact
from src.models.alchemy import EntranceTestStructure, Problem, ProblemTypePrerequisite
from src.models.pydantic import (
    EntranceTestCompiledForestPayload,
    EntranceTestCompiledGraphPayload,
    EntranceTestCompiledStructurePayload,
    EntranceTestStructureCompileResponse,
    EntranceTestStructureSnapshot,
    EntranceTestStructureState,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class EntranceTestStructureCompileError(RuntimeError):
    pass


class EntranceTestStructureNotForestError(EntranceTestStructureCompileError):
    pass


class EntranceTestStructureNotCompiledError(RuntimeError):
    pass


class EntranceTestStructureCompilationFailedError(RuntimeError):
    pass


class EntranceTestStructureService:
    def __init__(self) -> None:
        self.branch_penalty_exponent = float(
            EnvTools.required_load_env_var(
                "ENTRANCE_ASSESSMENT_BRANCH_PENALTY_EXPONENT"
            )
        )
        self.artifact_kind = "exact_forest_v1"


    async def build_live_snapshot(
        self,
        session: "AsyncSession",
    ) -> EntranceTestStructureSnapshot:
        problem_type_ids = await self._load_active_problem_type_ids(session)
        if not problem_type_ids:
            raise ValueError("Entrance test does not have active problem types")

        prerequisite_edges = await self._load_prerequisite_edges(
            session=session,
            active_problem_type_ids=set(problem_type_ids),
        )
        source_hash = self._build_source_hash(
            problem_type_ids=problem_type_ids,
            prerequisite_edges=prerequisite_edges,
        )
        structure_version = self._build_structure_version(source_hash)
        snapshot = EntranceTestStructureSnapshot(
            problem_type_ids=list(problem_type_ids),
            prerequisite_edges=list(prerequisite_edges),
            structure_version=structure_version,
            source_hash=source_hash,
            problem_type_count=len(problem_type_ids),
            edge_count=len(prerequisite_edges),
        )
        logger.info(
            "Built live entrance test structure snapshot: structure_version={}, problem_type_count={}, edge_count={}",
            snapshot.structure_version,
            snapshot.problem_type_count,
            snapshot.edge_count,
        )
        return snapshot


    async def compile_current_structure(
        self,
        session: "AsyncSession",
    ) -> EntranceTestStructureCompileResponse:
        snapshot = await self.build_live_snapshot(session)
        stored_structure = await self._load_structure_record(
            session=session,
            structure_version=snapshot.structure_version,
        )

        if (
            stored_structure is not None
            and stored_structure.source_hash == snapshot.source_hash
            and stored_structure.status == EntranceTestStructureStatus.READY
            and stored_structure.compiled_payload is not None
        ):
            logger.info(
                "Reused compiled entrance test structure: structure_version={}, problem_type_count={}, edge_count={}, feasible_state_count={}",
                stored_structure.structure_version,
                stored_structure.problem_type_count,
                stored_structure.edge_count,
                stored_structure.feasible_state_count,
            )
            return self._build_compile_response(stored_structure)

        try:
            structure_state = self._compile_snapshot(snapshot)
        except EntranceTestStructureCompileError as error:
            failed_structure = await self._upsert_structure_record(
                session=session,
                snapshot=snapshot,
                status=EntranceTestStructureStatus.FAILED,
                feasible_state_count=0,
                compiled_payload=None,
                error_message=str(error),
            )
            logger.warning(
                "Stored failed entrance test structure compilation: structure_version={}, error_message={}",
                failed_structure.structure_version,
                failed_structure.error_message,
            )
            return self._build_compile_response(failed_structure)

        compiled_payload = self._serialize_compiled_payload(
            self._build_compiled_payload(structure_state)
        )
        ready_structure = await self._upsert_structure_record(
            session=session,
            snapshot=snapshot,
            status=EntranceTestStructureStatus.READY,
            feasible_state_count=structure_state.feasible_state_count,
            compiled_payload=compiled_payload,
            error_message=None,
        )
        logger.info(
            "Stored compiled entrance test structure: structure_version={}, problem_type_count={}, edge_count={}, feasible_state_count={}, roots={}, max_depth={}, payload_bytes={}",
            ready_structure.structure_version,
            ready_structure.problem_type_count,
            ready_structure.edge_count,
            ready_structure.feasible_state_count,
            len(structure_state.forest_artifact.root_indices),
            structure_state.forest_artifact.max_depth,
            len(compiled_payload),
        )
        return self._build_compile_response(ready_structure)


    async def load_latest_compiled_structure(
        self,
        session: "AsyncSession",
    ) -> EntranceTestStructureState:
        snapshot = await self.build_live_snapshot(session)
        return await self.load_compiled_structure(
            session=session,
            structure_version=snapshot.structure_version,
        )


    async def load_compiled_structure(
        self,
        session: "AsyncSession",
        structure_version: int,
    ) -> EntranceTestStructureState:
        stored_structure = await self._load_structure_record(session, structure_version)
        if stored_structure is None:
            raise EntranceTestStructureNotCompiledError(
                f"Entrance test structure version {structure_version} is not compiled"
            )

        if (
            stored_structure.status != EntranceTestStructureStatus.READY
            or stored_structure.compiled_payload is None
        ):
            raise EntranceTestStructureCompilationFailedError(
                stored_structure.error_message
                or f"Entrance test structure version {structure_version} is not ready"
            )

        payload = self._deserialize_compiled_payload(stored_structure.compiled_payload)
        structure_state = self._build_structure_state(
            structure_version=stored_structure.structure_version,
            feasible_state_count=int(stored_structure.feasible_state_count),
            payload=payload,
        )
        logger.info(
            "Loaded compiled entrance test structure: structure_version={}, problem_type_count={}, edge_count={}, feasible_state_count={}, roots={}, max_depth={}",
            stored_structure.structure_version,
            stored_structure.problem_type_count,
            stored_structure.edge_count,
            stored_structure.feasible_state_count,
            len(structure_state.forest_artifact.root_indices),
            structure_state.forest_artifact.max_depth,
        )
        return structure_state


    async def _load_active_problem_type_ids(
        self,
        session: "AsyncSession",
    ) -> tuple[uuid.UUID, ...]:
        result = await session.execute(
            select(Problem.problem_type_id)
            .group_by(Problem.problem_type_id)
            .order_by(Problem.problem_type_id)
        )
        return tuple(result.scalars().all())


    async def _load_prerequisite_edges(
        self,
        session: "AsyncSession",
        active_problem_type_ids: set[uuid.UUID],
    ) -> tuple[tuple[uuid.UUID, uuid.UUID], ...]:
        result = await session.execute(
            select(
                ProblemTypePrerequisite.problem_type_id,
                ProblemTypePrerequisite.prerequisite_problem_type_id,
            )
        )
        return tuple(
            sorted(
                (
                    (problem_type_id, prerequisite_problem_type_id)
                    for problem_type_id, prerequisite_problem_type_id in result.all()
                    if problem_type_id in active_problem_type_ids
                    and prerequisite_problem_type_id in active_problem_type_ids
                ),
                key=lambda edge: (str(edge[0]), str(edge[1])),
            )
        )


    async def _load_structure_record(
        self,
        session: "AsyncSession",
        structure_version: int,
    ) -> EntranceTestStructure | None:
        result = await session.execute(
            select(EntranceTestStructure).where(
                EntranceTestStructure.structure_version == structure_version
            )
        )
        return result.scalar_one_or_none()


    async def _upsert_structure_record(
        self,
        session: "AsyncSession",
        snapshot: EntranceTestStructureSnapshot,
        status: EntranceTestStructureStatus,
        feasible_state_count: int,
        compiled_payload: bytes | None,
        error_message: str | None,
    ) -> EntranceTestStructure:
        stored_structure = await self._load_structure_record(
            session=session,
            structure_version=snapshot.structure_version,
        )
        if stored_structure is None:
            stored_structure = EntranceTestStructure(
                structure_version=snapshot.structure_version,
                source_hash=snapshot.source_hash,
                artifact_kind=self.artifact_kind,
                status=status,
                problem_type_count=snapshot.problem_type_count,
                edge_count=snapshot.edge_count,
                feasible_state_count=feasible_state_count,
                compiled_payload=compiled_payload,
                error_message=error_message,
            )
            session.add(stored_structure)
        else:
            stored_structure.source_hash = snapshot.source_hash
            stored_structure.artifact_kind = self.artifact_kind
            stored_structure.status = status
            stored_structure.problem_type_count = snapshot.problem_type_count
            stored_structure.edge_count = snapshot.edge_count
            stored_structure.feasible_state_count = feasible_state_count
            stored_structure.compiled_payload = compiled_payload
            stored_structure.error_message = error_message

        await session.flush()
        return stored_structure


    def _build_source_hash(
        self,
        problem_type_ids: tuple[uuid.UUID, ...],
        prerequisite_edges: tuple[tuple[uuid.UUID, uuid.UUID], ...],
    ) -> str:
        source_value = "|".join(
            [
                self.artifact_kind,
                str(self.branch_penalty_exponent),
                "problem_types",
                *[str(problem_type_id) for problem_type_id in problem_type_ids],
                "edges",
                *[
                    f"{problem_type_id}:{prerequisite_problem_type_id}"
                    for problem_type_id, prerequisite_problem_type_id in prerequisite_edges
                ],
            ]
        )
        return StringTools.hash_string(source_value)


    @staticmethod
    def _build_structure_version(source_hash: str) -> int:
        structure_version = int(source_hash[:12], 16) % 2_147_483_647
        return structure_version or 1


    def _compile_snapshot(
        self,
        snapshot: EntranceTestStructureSnapshot,
    ) -> EntranceTestStructureState:
        graph_artifact = build_graph_artifact(
            problem_type_ids=tuple(snapshot.problem_type_ids),
            prerequisite_edges=tuple(snapshot.prerequisite_edges),
            branch_penalty_exponent=self.branch_penalty_exponent,
        )
        try:
            forest_artifact = build_forest_artifact(graph_artifact)
        except ForestStructureError as error:
            raise EntranceTestStructureNotForestError(str(error)) from error

        logger.info(
            "Compiled exact forest entrance test structure snapshot: structure_version={}, problem_type_count={}, edge_count={}, feasible_state_count={}, roots={}, component_sizes={}, max_depth={}",
            snapshot.structure_version,
            snapshot.problem_type_count,
            snapshot.edge_count,
            forest_artifact.feasible_state_count,
            len(forest_artifact.root_indices),
            forest_artifact.component_sizes,
            forest_artifact.max_depth,
        )
        return EntranceTestStructureState(
            graph_artifact=graph_artifact,
            forest_artifact=forest_artifact,
            structure_version=snapshot.structure_version,
            feasible_state_count=forest_artifact.feasible_state_count,
        )


    def _build_compile_response(
        self,
        stored_structure: EntranceTestStructure,
    ) -> EntranceTestStructureCompileResponse:
        return EntranceTestStructureCompileResponse(
            structure_version=stored_structure.structure_version,
            status=stored_structure.status,
            artifact_kind=stored_structure.artifact_kind,
            problem_type_count=stored_structure.problem_type_count,
            edge_count=stored_structure.edge_count,
            feasible_state_count=int(stored_structure.feasible_state_count),
            error_message=stored_structure.error_message,
        )


    def _build_compiled_payload(
        self,
        structure_state: EntranceTestStructureState,
    ) -> EntranceTestCompiledStructurePayload:
        graph_artifact = structure_state.graph_artifact
        forest_artifact = structure_state.forest_artifact
        return EntranceTestCompiledStructurePayload(
            graph_artifact=EntranceTestCompiledGraphPayload(
                node_ids=list(graph_artifact.node_ids),
                prerequisites_by_index=[
                    list(indices)
                    for indices in graph_artifact.prerequisites_by_index
                ],
                dependents_by_index=[
                    list(indices)
                    for indices in graph_artifact.dependents_by_index
                ],
                indegree_by_index=graph_artifact.indegree_by_index.astype(np.int64).tolist(),
                topological_order=list(graph_artifact.topological_order),
                ancestors_by_index=[
                    list(indices)
                    for indices in graph_artifact.ancestors_by_index
                ],
                descendants_by_index=[
                    list(indices)
                    for indices in graph_artifact.descendants_by_index
                ],
                ancestor_distances_to_index=[
                    dict(distances)
                    for distances in graph_artifact.ancestor_distances_to_index
                ],
                descendant_distances_from_index=[
                    dict(distances)
                    for distances in graph_artifact.descendant_distances_from_index
                ],
                descendant_branch_support_from_index=[
                    dict(branch_support)
                    for branch_support in graph_artifact.descendant_branch_support_from_index
                ],
            ),
            forest_artifact=EntranceTestCompiledForestPayload(
                parent_by_index=list(forest_artifact.parent_by_index),
                children_by_index=[
                    list(indices)
                    for indices in forest_artifact.children_by_index
                ],
                root_indices=list(forest_artifact.root_indices),
                preorder_indices=list(forest_artifact.preorder_indices),
                postorder_indices=list(forest_artifact.postorder_indices),
                depth_by_index=list(forest_artifact.depth_by_index),
                component_sizes=list(forest_artifact.component_sizes),
                max_depth=forest_artifact.max_depth,
                feasible_state_count=forest_artifact.feasible_state_count,
                initial_entropy=forest_artifact.initial_entropy,
            ),
        )


    @staticmethod
    def _serialize_compiled_payload(
        payload: EntranceTestCompiledStructurePayload,
    ) -> bytes:
        return gzip.compress(payload.model_dump_json().encode("utf-8"))


    @staticmethod
    def _deserialize_compiled_payload(
        compiled_payload: bytes,
    ) -> EntranceTestCompiledStructurePayload:
        return EntranceTestCompiledStructurePayload.model_validate_json(
            gzip.decompress(compiled_payload)
        )


    def _build_structure_state(
        self,
        structure_version: int,
        feasible_state_count: int,
        payload: EntranceTestCompiledStructurePayload,
    ) -> EntranceTestStructureState:
        node_ids = tuple(payload.graph_artifact.node_ids)
        graph_artifact = GraphArtifact(
            node_ids=node_ids,
            index_by_id={
                problem_type_id: index
                for index, problem_type_id in enumerate(node_ids)
            },
            prerequisites_by_index=tuple(
                tuple(indices)
                for indices in payload.graph_artifact.prerequisites_by_index
            ),
            dependents_by_index=tuple(
                tuple(indices)
                for indices in payload.graph_artifact.dependents_by_index
            ),
            indegree_by_index=np.asarray(
                payload.graph_artifact.indegree_by_index,
                dtype=np.int64,
            ),
            topological_order=tuple(payload.graph_artifact.topological_order),
            ancestors_by_index=tuple(
                tuple(indices)
                for indices in payload.graph_artifact.ancestors_by_index
            ),
            descendants_by_index=tuple(
                tuple(indices)
                for indices in payload.graph_artifact.descendants_by_index
            ),
            ancestor_distances_to_index=tuple(
                dict(distances)
                for distances in payload.graph_artifact.ancestor_distances_to_index
            ),
            descendant_distances_from_index=tuple(
                dict(distances)
                for distances in payload.graph_artifact.descendant_distances_from_index
            ),
            descendant_branch_support_from_index=tuple(
                dict(branch_support)
                for branch_support in payload.graph_artifact.descendant_branch_support_from_index
            ),
        )
        forest_artifact = ForestArtifact(
            parent_by_index=tuple(payload.forest_artifact.parent_by_index),
            children_by_index=tuple(
                tuple(indices)
                for indices in payload.forest_artifact.children_by_index
            ),
            root_indices=tuple(payload.forest_artifact.root_indices),
            preorder_indices=tuple(payload.forest_artifact.preorder_indices),
            postorder_indices=tuple(payload.forest_artifact.postorder_indices),
            depth_by_index=tuple(payload.forest_artifact.depth_by_index),
            component_sizes=tuple(payload.forest_artifact.component_sizes),
            max_depth=payload.forest_artifact.max_depth,
            feasible_state_count=payload.forest_artifact.feasible_state_count,
            initial_entropy=payload.forest_artifact.initial_entropy,
        )
        return EntranceTestStructureState(
            graph_artifact=graph_artifact,
            forest_artifact=forest_artifact,
            structure_version=structure_version,
            feasible_state_count=feasible_state_count,
        )
