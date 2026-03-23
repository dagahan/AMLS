from __future__ import annotations

import uuid

from loguru import logger
import numpy as np

from src.math_models.entrance_assessment.evidence_update import (
    apply_node_score_increment,
)
from src.math_models.entrance_assessment.probability import solve_forest_posterior
from src.math_models.entrance_assessment.selection import select_next_problem_type
from src.math_models.entrance_assessment.state_scoring import (
    calculate_node_score_increment,
)
from src.math_models.entrance_assessment.stopping import should_stop
from src.math_models.entrance_assessment.support_profile import build_support_profile
from src.math_models.entrance_assessment.types import (
    FinalAssessmentResult,
    ForestArtifact,
    GraphArtifact,
    Outcome,
    RuntimeSnapshot,
    StepResult,
)

DEFAULT_MASTERED_PROBABILITY = 0.85


def initialize_runtime(
    forest_artifact: ForestArtifact,
    temperature_sharpening: float,
) -> RuntimeSnapshot:
    node_count = len(forest_artifact.parent_by_index)
    if node_count <= 0:
        raise ValueError("Forest artifact must contain at least one problem type")

    node_scores = np.zeros(node_count, dtype=np.float64)
    (
        marginal_probabilities,
        current_entropy,
        current_temperature,
        leader_problem_type_indices,
        leader_state_index,
        leader_state_probability,
    ) = solve_forest_posterior(
        forest_artifact=forest_artifact,
        node_scores=node_scores,
        initial_entropy=forest_artifact.initial_entropy,
        temperature_sharpening=temperature_sharpening,
        initial_temperature=1.0,
    )

    return RuntimeSnapshot(
        node_scores=node_scores,
        marginal_probabilities=marginal_probabilities,
        initial_entropy=forest_artifact.initial_entropy,
        current_entropy=current_entropy,
        current_temperature=current_temperature,
        asked_problem_type_indices=tuple(),
        leader_state_index=leader_state_index,
        leader_state_probability=leader_state_probability,
        leader_problem_type_indices=leader_problem_type_indices,
    )


def apply_answer_step(
    graph_artifact: GraphArtifact,
    forest_artifact: ForestArtifact,
    runtime: RuntimeSnapshot,
    answered_problem_type_id: uuid.UUID,
    outcome: Outcome,
    instance_difficulty_weight: float,
    i_dont_know_scalar: float,
    ancestor_support_correct: float,
    ancestor_support_wrong: float,
    descendant_support_correct: float,
    descendant_support_wrong: float,
    ancestor_decay: float,
    descendant_decay: float,
    temperature_sharpening: float,
    entropy_stop: float,
    utility_stop: float,
    leader_probability_stop: float | None,
    max_questions: int,
    epsilon: float,
    available_problem_type_ids: set[uuid.UUID] | None = None,
) -> StepResult:
    answered_problem_type_index = _resolve_problem_type_index(
        graph_artifact=graph_artifact,
        problem_type_id=answered_problem_type_id,
    )
    available_problem_type_indices = _resolve_available_indices(
        graph_artifact=graph_artifact,
        available_problem_type_ids=available_problem_type_ids,
    )
    support_profile = build_support_profile(
        graph_artifact=graph_artifact,
        answered_problem_type_index=answered_problem_type_index,
        outcome=outcome,
        i_dont_know_scalar=i_dont_know_scalar,
        ancestor_support_correct=ancestor_support_correct,
        ancestor_support_wrong=ancestor_support_wrong,
        descendant_support_correct=descendant_support_correct,
        descendant_support_wrong=descendant_support_wrong,
        ancestor_decay=ancestor_decay,
        descendant_decay=descendant_decay,
    )
    node_score_increment = calculate_node_score_increment(
        support_profile=support_profile,
        instance_difficulty_weight=instance_difficulty_weight,
        epsilon=epsilon,
    )
    next_node_scores = apply_node_score_increment(
        runtime=runtime,
        node_score_increment=node_score_increment,
    )
    (
        next_marginal_probabilities,
        next_entropy,
        next_temperature,
        leader_problem_type_indices,
        leader_state_index,
        leader_state_probability,
    ) = solve_forest_posterior(
        forest_artifact=forest_artifact,
        node_scores=next_node_scores,
        initial_entropy=runtime.initial_entropy,
        temperature_sharpening=temperature_sharpening,
        initial_temperature=runtime.current_temperature,
    )
    asked_problem_type_indices = tuple(
        sorted(set(runtime.asked_problem_type_indices) | {answered_problem_type_index})
    )
    logger.debug(
        "Applied forest entrance assessment step: answered_problem_type_id={}, outcome={}, difficulty_weight={}, entropy={}, temperature={}, leader_probability={}",
        answered_problem_type_id,
        outcome,
        instance_difficulty_weight,
        next_entropy,
        next_temperature,
        leader_state_probability,
    )
    next_runtime = RuntimeSnapshot(
        node_scores=next_node_scores,
        marginal_probabilities=next_marginal_probabilities,
        initial_entropy=runtime.initial_entropy,
        current_entropy=next_entropy,
        current_temperature=next_temperature,
        asked_problem_type_indices=asked_problem_type_indices,
        leader_state_index=leader_state_index,
        leader_state_probability=leader_state_probability,
        leader_problem_type_indices=leader_problem_type_indices,
    )
    selection = select_next_problem_type(
        graph_artifact=graph_artifact,
        runtime=next_runtime,
        available_problem_type_indices=available_problem_type_indices,
    )
    stop, stop_reason = should_stop(
        runtime=next_runtime,
        selection=selection,
        entropy_stop=entropy_stop,
        utility_stop=utility_stop,
        leader_probability_stop=leader_probability_stop,
        max_questions=max_questions,
    )

    return StepResult(
        runtime=next_runtime,
        selection=selection,
        should_stop=stop,
        stop_reason=stop_reason,
    )


def build_final_result(
    graph_artifact: GraphArtifact,
    runtime: RuntimeSnapshot,
) -> FinalAssessmentResult:
    learned_indices = tuple(
        index
        for index, marginal_probability in enumerate(runtime.marginal_probabilities)
        if float(marginal_probability) >= DEFAULT_MASTERED_PROBABILITY
    )
    learned_index_set = set(learned_indices)
    outer_fringe_indices = tuple(
        node_index
        for node_index in range(len(graph_artifact.node_ids))
        if node_index not in learned_index_set
        and all(
            prerequisite_index in learned_index_set
            for prerequisite_index in graph_artifact.prerequisites_by_index[node_index]
        )
    )
    outer_fringe_index_set = set(outer_fringe_indices)
    inner_fringe_indices = tuple(
        node_index
        for node_index in learned_indices
        if any(
            dependent_index in outer_fringe_index_set
            for dependent_index in graph_artifact.dependents_by_index[node_index]
        )
    )

    logger.info(
        "Built entrance assessment final result: leader_state_index={}, leader_state_probability={}, learned_count={}, inner_fringe_count={}, outer_fringe_count={}, normalized_entropy={}",
        runtime.leader_state_index,
        runtime.leader_state_probability,
        len(learned_indices),
        len(inner_fringe_indices),
        len(outer_fringe_indices),
        runtime.normalized_entropy,
    )

    return FinalAssessmentResult(
        state_index=runtime.leader_state_index,
        state_probability=runtime.leader_state_probability,
        learned_problem_type_indices=learned_indices,
        learned_problem_type_ids=tuple(
            graph_artifact.node_ids[index]
            for index in learned_indices
        ),
        inner_fringe_indices=inner_fringe_indices,
        inner_fringe_ids=tuple(
            graph_artifact.node_ids[index]
            for index in inner_fringe_indices
        ),
        outer_fringe_indices=outer_fringe_indices,
        outer_fringe_ids=tuple(
            graph_artifact.node_ids[index]
            for index in outer_fringe_indices
        ),
    )


def _resolve_problem_type_index(
    graph_artifact: GraphArtifact,
    problem_type_id: uuid.UUID,
) -> int:
    try:
        return graph_artifact.index_by_id[problem_type_id]
    except KeyError as error:
        raise ValueError(f"Unknown problem type id: {problem_type_id}") from error


def _resolve_available_indices(
    graph_artifact: GraphArtifact,
    available_problem_type_ids: set[uuid.UUID] | None,
) -> set[int] | None:
    if available_problem_type_ids is None:
        return None

    return {
        graph_artifact.index_by_id[problem_type_id]
        for problem_type_id in available_problem_type_ids
        if problem_type_id in graph_artifact.index_by_id
    }
