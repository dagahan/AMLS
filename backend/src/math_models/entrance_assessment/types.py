from __future__ import annotations

import uuid
from enum import StrEnum
from typing import TypeAlias

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict

ProblemTypeId: TypeAlias = uuid.UUID
FloatVector: TypeAlias = NDArray[np.float64]
IntVector: TypeAlias = NDArray[np.int64]
Int8Matrix: TypeAlias = NDArray[np.int8]


class EntranceAssessmentSchema(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        frozen=True,
    )


class Outcome(StrEnum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    I_DONT_KNOW = "i_dont_know"


class GraphArtifact(EntranceAssessmentSchema):
    node_ids: tuple[ProblemTypeId, ...]
    index_by_id: dict[ProblemTypeId, int]
    prerequisites_by_index: tuple[tuple[int, ...], ...]
    dependents_by_index: tuple[tuple[int, ...], ...]
    indegree_by_index: IntVector
    topological_order: tuple[int, ...]
    ancestors_by_index: tuple[tuple[int, ...], ...]
    descendants_by_index: tuple[tuple[int, ...], ...]
    ancestor_distances_to_index: tuple[dict[int, int], ...]
    descendant_distances_from_index: tuple[dict[int, int], ...]
    descendant_branch_support_from_index: tuple[dict[int, float], ...]


class ForestArtifact(EntranceAssessmentSchema):
    parent_by_index: tuple[int | None, ...]
    children_by_index: tuple[tuple[int, ...], ...]
    root_indices: tuple[int, ...]
    preorder_indices: tuple[int, ...]
    postorder_indices: tuple[int, ...]
    depth_by_index: tuple[int, ...]
    component_sizes: tuple[int, ...]
    max_depth: int
    feasible_state_count: int
    initial_entropy: float


class StateArtifact(EntranceAssessmentSchema):
    state_masks: tuple[int, ...]
    state_index_by_mask: dict[int, int]
    state_sign_matrix: Int8Matrix
    states_containing_node_indices: tuple[IntVector, ...]
    initial_entropy: float


class RuntimeSnapshot(EntranceAssessmentSchema):
    node_scores: FloatVector
    marginal_probabilities: FloatVector
    initial_entropy: float
    current_entropy: float
    current_temperature: float
    asked_problem_type_indices: tuple[int, ...]
    leader_state_index: int
    leader_state_probability: float
    leader_problem_type_indices: tuple[int, ...]


class SelectionResult(EntranceAssessmentSchema):
    problem_type_index: int | None
    problem_type_id: ProblemTypeId | None
    marginal_probabilities: FloatVector
    utilities: FloatVector
    max_utility: float


class StepResult(EntranceAssessmentSchema):
    runtime: RuntimeSnapshot
    selection: SelectionResult
    should_stop: bool
    stop_reason: str | None


class FinalAssessmentResult(EntranceAssessmentSchema):
    state_index: int
    state_probability: float
    learned_problem_type_indices: tuple[int, ...]
    learned_problem_type_ids: tuple[ProblemTypeId, ...]
    inner_fringe_indices: tuple[int, ...]
    inner_fringe_ids: tuple[ProblemTypeId, ...]
    outer_fringe_indices: tuple[int, ...]
    outer_fringe_ids: tuple[ProblemTypeId, ...]
