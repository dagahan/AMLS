from __future__ import annotations

import uuid
from enum import StrEnum
from typing import TypeAlias

import numpy as np
from numpy.typing import NDArray
from pydantic import ConfigDict

from src.models.pydantic.common import AmlsSchema


ProblemTypeId: TypeAlias = uuid.UUID
FloatVector: TypeAlias = NDArray[np.float64]
IntVector: TypeAlias = NDArray[np.int64]


class EntranceAssessmentSchema(AmlsSchema):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        arbitrary_types_allowed=True,
        frozen=True,
    )


class Outcome(StrEnum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    I_DONT_KNOW = "i_dont_know"


class ResponseModel(EntranceAssessmentSchema):
    mastered_right: float
    mastered_wrong: float
    mastered_i_dont_know: float
    unmastered_right: float
    unmastered_wrong: float
    unmastered_i_dont_know: float


class GraphArtifact(EntranceAssessmentSchema):
    node_ids: tuple[ProblemTypeId, ...]
    index_by_id: dict[ProblemTypeId, int]
    prerequisites_by_index: tuple[tuple[int, ...], ...]
    dependents_by_index: tuple[tuple[int, ...], ...]
    indegree_by_index: IntVector
    topological_order: tuple[int, ...]


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


class Selection(EntranceAssessmentSchema):
    problem_type_id: ProblemTypeId | None
    problem_type_index: int | None
    mastery_probability: float
    max_utility: float


class ProjectionSnapshot(EntranceAssessmentSchema):
    learned_problem_type_indices: tuple[int, ...]
    inner_fringe_problem_type_indices: tuple[int, ...]
    outer_fringe_problem_type_indices: tuple[int, ...]
    uncertain_problem_type_indices: tuple[int, ...]
    projection_confidence: float
    frontier_confidence: float


class RuntimeSnapshot(EntranceAssessmentSchema):
    node_scores: FloatVector
    marginal_probabilities: FloatVector
    initial_entropy: float
    current_entropy: float
    current_temperature: float
    asked_problem_type_indices: tuple[int, ...]
    leader_state_index: int | None
    leader_state_probability: float
    leader_problem_type_indices: tuple[int, ...]


    @property
    def normalized_entropy(self) -> float:
        if self.initial_entropy <= 0.0:
            return 0.0

        normalized_entropy = self.current_entropy / self.initial_entropy
        return max(0.0, min(1.0, normalized_entropy))


class StepResult(EntranceAssessmentSchema):
    runtime: RuntimeSnapshot
    selection: Selection
    should_stop: bool
    stop_reason: str | None


class FinalResult(EntranceAssessmentSchema):
    state_index: int
    state_probability: float
    learned_problem_type_ids: tuple[ProblemTypeId, ...]
    inner_fringe_ids: tuple[ProblemTypeId, ...]
    outer_fringe_ids: tuple[ProblemTypeId, ...]
