from __future__ import annotations

import uuid
from enum import StrEnum
from typing import TypeAlias

import numpy as np
from numpy.typing import NDArray
from pydantic import ConfigDict

from src.models.pydantic.common import AmlsSchema


NodeId: TypeAlias = uuid.UUID
FloatVector: TypeAlias = NDArray[np.float64]
IntVector: TypeAlias = NDArray[np.int64]


class AssessmentRuntimeSchema(AmlsSchema):
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


class ResponseModel(AssessmentRuntimeSchema):
    mastered_right: float
    mastered_wrong: float
    mastered_i_dont_know: float
    unmastered_right: float
    unmastered_wrong: float
    unmastered_i_dont_know: float


class GraphArtifact(AssessmentRuntimeSchema):
    node_ids: tuple[NodeId, ...]
    index_by_id: dict[NodeId, int]
    prerequisites_by_index: tuple[tuple[int, ...], ...]
    dependents_by_index: tuple[tuple[int, ...], ...]
    indegree_by_index: IntVector
    topological_order: tuple[int, ...]


class ExactInferenceArtifact(AssessmentRuntimeSchema):
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


class Selection(AssessmentRuntimeSchema):
    node_id: NodeId | None
    node_index: int | None
    mastery_probability: float
    max_utility: float


class ProjectionSnapshot(AssessmentRuntimeSchema):
    learned_node_indices: tuple[int, ...]
    inner_fringe_node_indices: tuple[int, ...]
    outer_fringe_node_indices: tuple[int, ...]
    uncertain_node_indices: tuple[int, ...]
    projection_confidence: float
    frontier_confidence: float


class RuntimeSnapshot(AssessmentRuntimeSchema):
    node_scores: FloatVector
    marginal_probabilities: FloatVector
    initial_entropy: float
    current_entropy: float
    current_temperature: float
    asked_node_indices: tuple[int, ...]
    leader_state_index: int | None
    leader_state_probability: float
    leader_node_indices: tuple[int, ...]


    @property
    def normalized_entropy(self) -> float:
        if self.initial_entropy <= 0.0:
            return 0.0

        normalized_entropy = self.current_entropy / self.initial_entropy
        return max(0.0, min(1.0, normalized_entropy))


class StepResult(AssessmentRuntimeSchema):
    runtime: RuntimeSnapshot
    selection: Selection
    should_stop: bool
    stop_reason: str | None


class FinalResult(AssessmentRuntimeSchema):
    state_index: int
    state_probability: float
    learned_node_ids: tuple[NodeId, ...]
    inner_fringe_node_ids: tuple[NodeId, ...]
    outer_fringe_node_ids: tuple[NodeId, ...]
