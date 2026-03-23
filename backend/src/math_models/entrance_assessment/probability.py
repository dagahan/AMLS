from __future__ import annotations

from time import perf_counter

from loguru import logger
import numpy as np

from src.math_models.entrance_assessment.temperature import calculate_temperature
from src.math_models.entrance_assessment.types import FloatVector, ForestArtifact

STATE_INDEX_MODULUS = 2_147_483_647


def solve_forest_posterior(
    forest_artifact: ForestArtifact,
    node_scores: FloatVector,
    initial_entropy: float,
    temperature_sharpening: float,
    initial_temperature: float | None = None,
) -> tuple[FloatVector, float, float, tuple[int, ...], int, float]:
    current_temperature = (
        float(initial_temperature)
        if initial_temperature is not None and initial_temperature > 0.0
        else 1.0
    )

    (
        marginal_probabilities,
        current_entropy,
        leader_problem_type_indices,
        leader_state_index,
        leader_state_probability,
    ) = calculate_forest_posterior(
        forest_artifact=forest_artifact,
        node_scores=node_scores,
        temperature=current_temperature,
    )
    next_temperature = calculate_temperature(
        current_entropy=current_entropy,
        initial_entropy=initial_entropy,
        temperature_sharpening=temperature_sharpening,
    )

    logger.debug(
        "Solved forest entrance assessment posterior: previous_temperature={}, provisional_entropy={}, next_temperature={}",
        current_temperature,
        current_entropy,
        next_temperature,
    )

    (
        marginal_probabilities,
        current_entropy,
        leader_problem_type_indices,
        leader_state_index,
        leader_state_probability,
    ) = calculate_forest_posterior(
        forest_artifact=forest_artifact,
        node_scores=node_scores,
        temperature=next_temperature,
    )

    return (
        marginal_probabilities,
        current_entropy,
        next_temperature,
        leader_problem_type_indices,
        leader_state_index,
        leader_state_probability,
    )


def calculate_forest_posterior(
    forest_artifact: ForestArtifact,
    node_scores: FloatVector,
    temperature: float,
) -> tuple[FloatVector, float, tuple[int, ...], int, float]:
    started_at = perf_counter()
    node_count = len(forest_artifact.parent_by_index)
    log_included_weight = np.zeros(node_count, dtype=np.float64)
    log_subtree_partition = np.zeros(node_count, dtype=np.float64)

    for node_index in forest_artifact.postorder_indices:
        child_log_partition_sum = 0.0

        for child_index in forest_artifact.children_by_index[node_index]:
            child_log_partition_sum += float(log_subtree_partition[child_index])

        log_included_weight[node_index] = (
            float(temperature) * float(node_scores[node_index])
            + child_log_partition_sum
        )
        log_subtree_partition[node_index] = _logaddexp_zero(
            float(log_included_weight[node_index])
        )

    log_partition = float(
        sum(
            float(log_subtree_partition[root_index])
            for root_index in forest_artifact.root_indices
        )
    )
    marginal_probabilities = _build_marginal_probabilities(
        forest_artifact=forest_artifact,
        log_included_weight=log_included_weight,
        log_subtree_partition=log_subtree_partition,
    )
    current_entropy = _build_current_entropy(
        log_partition=log_partition,
        node_scores=node_scores,
        marginal_probabilities=marginal_probabilities,
        temperature=temperature,
    )
    leader_problem_type_indices = _build_leader_problem_type_indices(
        forest_artifact=forest_artifact,
        node_scores=node_scores,
        temperature=temperature,
    )
    leader_state_score = float(
        temperature
        * float(np.sum(node_scores[list(leader_problem_type_indices)]))
        if leader_problem_type_indices
        else 0.0
    )
    leader_state_probability = float(
        np.exp(leader_state_score - log_partition)
    )
    leader_state_index = _build_state_index(
        forest_artifact=forest_artifact,
        included_indices=leader_problem_type_indices,
    )
    elapsed_ms = (perf_counter() - started_at) * 1000

    logger.debug(
        "Built posterior summary: temperature={}, current_entropy={}, log_partition={}, leader_state_index={}, leader_state_probability={}, leader_size={}, elapsed_ms={:.3f}",
        temperature,
        current_entropy,
        log_partition,
        leader_state_index,
        leader_state_probability,
        len(leader_problem_type_indices),
        elapsed_ms,
    )

    return (
        marginal_probabilities,
        current_entropy,
        leader_problem_type_indices,
        leader_state_index,
        leader_state_probability,
    )


def _build_marginal_probabilities(
    forest_artifact: ForestArtifact,
    log_included_weight: FloatVector,
    log_subtree_partition: FloatVector,
) -> FloatVector:
    node_count = len(forest_artifact.parent_by_index)
    marginal_probabilities = np.zeros(node_count, dtype=np.float64)

    for root_index in forest_artifact.root_indices:
        marginal_probabilities[root_index] = float(
            np.exp(
                float(log_included_weight[root_index])
                - float(log_subtree_partition[root_index])
            )
        )
        stack = [root_index]

        while stack:
            node_index = stack.pop()
            parent_probability = float(marginal_probabilities[node_index])

            for child_index in forest_artifact.children_by_index[node_index]:
                include_given_parent = float(
                    np.exp(
                        float(log_included_weight[child_index])
                        - float(log_subtree_partition[child_index])
                    )
                )
                marginal_probabilities[child_index] = (
                    parent_probability * include_given_parent
                )
                stack.append(child_index)

    return marginal_probabilities


def _build_current_entropy(
    log_partition: float,
    node_scores: FloatVector,
    marginal_probabilities: FloatVector,
    temperature: float,
) -> float:
    expected_state_score = float(
        np.dot(marginal_probabilities, node_scores) * float(temperature)
    )
    return max(float(log_partition - expected_state_score), 0.0)


def _build_leader_problem_type_indices(
    forest_artifact: ForestArtifact,
    node_scores: FloatVector,
    temperature: float,
) -> tuple[int, ...]:
    node_count = len(forest_artifact.parent_by_index)
    best_included_score = np.zeros(node_count, dtype=np.float64)

    for node_index in forest_artifact.postorder_indices:
        candidate_score = float(temperature) * float(node_scores[node_index])

        for child_index in forest_artifact.children_by_index[node_index]:
            candidate_score += max(float(best_included_score[child_index]), 0.0)

        best_included_score[node_index] = candidate_score

    included_indices: list[int] = []

    for root_index in forest_artifact.root_indices:
        if float(best_included_score[root_index]) > 0.0:
            _collect_leader_indices(
                forest_artifact=forest_artifact,
                best_included_score=best_included_score,
                node_index=root_index,
                included_indices=included_indices,
            )

    return tuple(included_indices)


def _collect_leader_indices(
    forest_artifact: ForestArtifact,
    best_included_score: FloatVector,
    node_index: int,
    included_indices: list[int],
) -> None:
    included_indices.append(node_index)

    for child_index in forest_artifact.children_by_index[node_index]:
        if float(best_included_score[child_index]) > 0.0:
            _collect_leader_indices(
                forest_artifact=forest_artifact,
                best_included_score=best_included_score,
                node_index=child_index,
                included_indices=included_indices,
            )


def _build_state_index(
    forest_artifact: ForestArtifact,
    included_indices: tuple[int, ...],
) -> int:
    included_index_set = set(included_indices)
    subtree_state_counts = _build_subtree_state_counts(forest_artifact)
    state_index = 0
    radix = 1

    for root_index in forest_artifact.root_indices:
        subtree_index = _build_subtree_state_index(
            forest_artifact=forest_artifact,
            subtree_state_counts=subtree_state_counts,
            included_index_set=included_index_set,
            node_index=root_index,
        )
        state_index += subtree_index * radix
        radix *= subtree_state_counts[root_index]

    if state_index <= 0:
        return 1

    if state_index <= STATE_INDEX_MODULUS:
        return state_index

    return ((state_index - 1) % STATE_INDEX_MODULUS) + 1


def _build_subtree_state_counts(
    forest_artifact: ForestArtifact,
) -> tuple[int, ...]:
    subtree_state_counts = [1 for _ in forest_artifact.parent_by_index]

    for node_index in forest_artifact.postorder_indices:
        child_state_product = 1

        for child_index in forest_artifact.children_by_index[node_index]:
            child_state_product *= subtree_state_counts[child_index]

        subtree_state_counts[node_index] = 1 + child_state_product

    return tuple(subtree_state_counts)


def _build_subtree_state_index(
    forest_artifact: ForestArtifact,
    subtree_state_counts: tuple[int, ...],
    included_index_set: set[int],
    node_index: int,
) -> int:
    if node_index not in included_index_set:
        return 0

    subtree_index = 1
    radix = 1

    for child_index in forest_artifact.children_by_index[node_index]:
        child_index_value = _build_subtree_state_index(
            forest_artifact=forest_artifact,
            subtree_state_counts=subtree_state_counts,
            included_index_set=included_index_set,
            node_index=child_index,
        )
        subtree_index += child_index_value * radix
        radix *= subtree_state_counts[child_index]

    return subtree_index


def _logaddexp_zero(value: float) -> float:
    if value > 0.0:
        return value + float(np.log1p(np.exp(-value)))

    return float(np.log1p(np.exp(value)))
