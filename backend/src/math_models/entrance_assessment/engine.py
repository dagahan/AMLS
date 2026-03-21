from __future__ import annotations

import uuid

import numpy as np

from src.math_models.entrance_assessment.evidence_update import apply_state_increments
from src.math_models.entrance_assessment.fringes import (
    compute_inner_fringe_indices,
    compute_outer_fringe_indices,
    extract_problem_type_indices_from_mask,
)
from src.math_models.entrance_assessment.probability import calculate_state_probabilities
from src.math_models.entrance_assessment.selection import select_next_problem_type
from src.math_models.entrance_assessment.state_scoring import calculate_state_increments
from src.math_models.entrance_assessment.stopping import should_stop
from src.math_models.entrance_assessment.support_profile import build_support_profile
from src.math_models.entrance_assessment.temperature import calculate_temperature
from src.math_models.entrance_assessment.types import (
    FinalAssessmentResult,
    GraphArtifact,
    Outcome,
    RuntimeSnapshot,
    StateArtifact,
    StepResult,
)


def initialize_runtime(state_artifact: StateArtifact) -> RuntimeSnapshot:
    state_count = len(state_artifact.state_masks)
    if state_count <= 0:
        raise ValueError("State artifact must contain at least one feasible state")

    uniform_probability = 1.0 / float(state_count)
    probabilities = np.full(state_count, uniform_probability, dtype=np.float64)
    alpha = np.zeros(state_count, dtype=np.float64)
    beta = np.zeros(state_count, dtype=np.float64)
    z = np.zeros(state_count, dtype=np.float64)

    return RuntimeSnapshot(
        alpha=alpha,
        beta=beta,
        z=z,
        probabilities=probabilities,
        initial_entropy=state_artifact.initial_entropy,
        current_entropy=state_artifact.initial_entropy,
        current_temperature=1.0,
        asked_problem_type_indices=tuple(),
        leader_state_index=0,
        leader_state_probability=uniform_probability,
    )


def apply_answer_step(
    graph_artifact: GraphArtifact,
    state_artifact: StateArtifact,
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
    leader_probability_stop: float,
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
    state_increments = calculate_state_increments(
        state_artifact=state_artifact,
        support_profile=support_profile,
        instance_difficulty_weight=instance_difficulty_weight,
        epsilon=epsilon,
    )
    next_alpha, next_beta, next_z = apply_state_increments(
        runtime=runtime,
        state_increments=state_increments,
    )
    next_temperature = calculate_temperature(
        previous_entropy=runtime.current_entropy,
        initial_entropy=runtime.initial_entropy,
        temperature_sharpening=temperature_sharpening,
    )
    next_probabilities, next_entropy, leader_state_index, leader_state_probability = (
        calculate_state_probabilities(
            state_scores=next_z,
            temperature=next_temperature,
        )
    )
    asked_problem_type_indices = tuple(
        sorted(set(runtime.asked_problem_type_indices) | {answered_problem_type_index})
    )
    next_runtime = RuntimeSnapshot(
        alpha=next_alpha,
        beta=next_beta,
        z=next_z,
        probabilities=next_probabilities,
        initial_entropy=runtime.initial_entropy,
        current_entropy=next_entropy,
        current_temperature=next_temperature,
        asked_problem_type_indices=asked_problem_type_indices,
        leader_state_index=leader_state_index,
        leader_state_probability=leader_state_probability,
    )
    selection = select_next_problem_type(
        graph_artifact=graph_artifact,
        state_artifact=state_artifact,
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
    state_artifact: StateArtifact,
    runtime: RuntimeSnapshot,
) -> FinalAssessmentResult:
    state_index = runtime.leader_state_index
    state_probability = runtime.leader_state_probability
    state_mask = state_artifact.state_masks[state_index]
    learned_indices = extract_problem_type_indices_from_mask(state_mask)
    inner_fringe_indices = compute_inner_fringe_indices(
        state_artifact=state_artifact,
        state_mask=state_mask,
    )
    outer_fringe_indices = compute_outer_fringe_indices(
        graph_artifact=graph_artifact,
        state_artifact=state_artifact,
        state_mask=state_mask,
    )

    return FinalAssessmentResult(
        state_index=state_index,
        state_probability=state_probability,
        state_mask=state_mask,
        learned_problem_type_indices=learned_indices,
        learned_problem_type_ids=tuple(graph_artifact.node_ids[index] for index in learned_indices),
        inner_fringe_indices=inner_fringe_indices,
        inner_fringe_ids=tuple(graph_artifact.node_ids[index] for index in inner_fringe_indices),
        outer_fringe_indices=outer_fringe_indices,
        outer_fringe_ids=tuple(graph_artifact.node_ids[index] for index in outer_fringe_indices),
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
