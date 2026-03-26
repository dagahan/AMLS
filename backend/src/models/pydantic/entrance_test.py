from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from src.storage.db.enums import (
    DifficultyLevel,
    EntranceTestResultNodeStatus,
    EntranceTestStructureStatus,
    EntranceTestStatus,
    ProblemAnswerOptionType,
)
from src.models.pydantic.entrance_assessment import (
    FinalResult,
    ForestArtifact,
    GraphArtifact,
    Outcome,
)
from src.models.pydantic.common import AmlsSchema
from src.models.pydantic.problem import ProblemResponse
from src.models.pydantic.response import RecordedResponseResponse, RecordedResponseState

if TYPE_CHECKING:
    from src.models.alchemy.entrance_test import EntranceTestSession


class EntranceTestSessionResponse(AmlsSchema):
    id: UUID
    status: EntranceTestStatus
    structure_version: int
    current_problem_id: UUID | None
    final_result: "EntranceTestFinalResultResponse | None" = None
    started_at: datetime | None
    completed_at: datetime | None
    skipped_at: datetime | None


class EntranceTestCurrentProblemResponse(AmlsSchema):
    session: EntranceTestSessionResponse
    problem: ProblemResponse | None


class EntranceTestAnswerRequest(AmlsSchema):
    problem_id: UUID
    answer_option_id: UUID


class EntranceTestAnswerResponse(AmlsSchema):
    session: EntranceTestSessionResponse
    response: RecordedResponseResponse
    next_problem: ProblemResponse | None
    final_result: "EntranceTestFinalResultResponse | None"


class EntranceTestFinalResultResponse(AmlsSchema):
    state_index: int
    state_probability: float | None
    learned_problem_type_ids: list[UUID]
    inner_fringe_ids: list[UUID]
    outer_fringe_ids: list[UUID]


class EntranceTestResultGraphNodeResponse(AmlsSchema):
    id: UUID
    name: str
    topic_id: UUID
    topic_name: str
    subtopic_id: UUID
    subtopic_name: str
    status: EntranceTestResultNodeStatus
    is_frontier: bool


class EntranceTestResultGraphEdgeResponse(AmlsSchema):
    from_problem_type_id: UUID
    to_problem_type_id: UUID


class EntranceTestResultTopicSummaryResponse(AmlsSchema):
    topic_id: UUID
    topic_name: str
    total_problem_types: int
    learned_count: int
    ready_count: int
    frontier_count: int
    locked_count: int


class EntranceTestResultSubtopicSummaryResponse(AmlsSchema):
    subtopic_id: UUID
    subtopic_name: str
    topic_id: UUID
    topic_name: str
    total_problem_types: int
    learned_count: int
    ready_count: int
    frontier_count: int
    locked_count: int


class EntranceTestResultResponse(AmlsSchema):
    session: EntranceTestSessionResponse
    final_result: EntranceTestFinalResultResponse
    nodes: list[EntranceTestResultGraphNodeResponse]
    edges: list[EntranceTestResultGraphEdgeResponse]
    topic_summaries: list[EntranceTestResultTopicSummaryResponse]
    subtopic_summaries: list[EntranceTestResultSubtopicSummaryResponse]


class EntranceTestRuntimePayload(AmlsSchema):
    runtime_kind: str
    node_scores: list[float]
    marginal_probabilities: list[float]
    initial_entropy: float
    current_entropy: float
    current_temperature: float
    asked_problem_type_indices: list[int]
    leader_state_index: int | None
    leader_state_probability: float
    leader_problem_type_indices: list[int]
    structure_version: int


class EntranceTestStructureSnapshot(AmlsSchema):
    problem_type_ids: list[UUID]
    prerequisite_edges: list[tuple[UUID, UUID]]
    structure_version: int
    source_hash: str
    problem_type_count: int
    edge_count: int


class EntranceTestCompiledGraphPayload(AmlsSchema):
    node_ids: list[UUID]
    prerequisites_by_index: list[list[int]]
    dependents_by_index: list[list[int]]
    indegree_by_index: list[int]
    topological_order: list[int]


class EntranceTestCompiledForestPayload(AmlsSchema):
    parent_by_index: list[int | None]
    children_by_index: list[list[int]]
    root_indices: list[int]
    preorder_indices: list[int]
    postorder_indices: list[int]
    depth_by_index: list[int]
    component_sizes: list[int]
    max_depth: int
    feasible_state_count: int
    initial_entropy: float


class EntranceTestCompiledStructurePayload(AmlsSchema):
    graph_artifact: EntranceTestCompiledGraphPayload
    forest_artifact: EntranceTestCompiledForestPayload


class EntranceTestStructureState(AmlsSchema):
    graph_artifact: GraphArtifact
    forest_artifact: ForestArtifact
    structure_version: int
    feasible_state_count: int


class EntranceTestStructureCompileResponse(AmlsSchema):
    structure_version: int
    status: EntranceTestStructureStatus
    artifact_kind: str
    problem_type_count: int
    edge_count: int
    feasible_state_count: int
    error_message: str | None


class EntranceTestEvaluationState(AmlsSchema):
    problem_id: UUID
    problem_type_id: UUID
    answer_option_id: UUID
    answer_option_type: ProblemAnswerOptionType
    difficulty: DifficultyLevel
    outcome: Outcome
    difficulty_weight: float


class StoredEntranceTestAnswerState(AmlsSchema):
    session_id: UUID
    previous_status: EntranceTestStatus
    previous_current_problem_id: UUID | None
    previous_completed_at: datetime | None
    previous_final_result: "EntranceTestFinalResultResponse | None"
    previous_runtime_payload: EntranceTestRuntimePayload | None
    session: EntranceTestSessionResponse
    response_state: RecordedResponseState
    next_problem: ProblemResponse | None
    final_result: EntranceTestFinalResultResponse | None


def build_entrance_test_session_response(
    session: "EntranceTestSession",
) -> EntranceTestSessionResponse:
    return EntranceTestSessionResponse(
        id=session.id,
        status=session.status,
        structure_version=session.structure_version,
        current_problem_id=session.current_problem_id,
        final_result=build_entrance_test_persisted_result_response(session),
        started_at=session.started_at,
        completed_at=session.completed_at,
        skipped_at=session.skipped_at,
    )


def build_entrance_test_final_result_response(
    final_result: FinalResult,
) -> EntranceTestFinalResultResponse:
    return EntranceTestFinalResultResponse(
        state_index=final_result.state_index,
        state_probability=final_result.state_probability,
        learned_problem_type_ids=list(final_result.learned_problem_type_ids),
        inner_fringe_ids=list(final_result.inner_fringe_ids),
        outer_fringe_ids=list(final_result.outer_fringe_ids),
    )


def build_entrance_test_persisted_result_response(
    session: "EntranceTestSession",
) -> EntranceTestFinalResultResponse | None:
    if session.final_state_index is None:
        return None

    return EntranceTestFinalResultResponse(
        state_index=session.final_state_index,
        state_probability=session.final_state_probability,
        learned_problem_type_ids=list(session.learned_problem_type_ids),
        inner_fringe_ids=list(session.inner_fringe_problem_type_ids),
        outer_fringe_ids=list(session.outer_fringe_problem_type_ids),
    )
