from __future__ import annotations

import hashlib

from loguru import logger
import numpy as np

from src.math_models.entrance_assessment.temperature import calculate_temperature
from src.math_models.entrance_assessment.types import FloatVector, ForestArtifact


TEMPERATURE_SOLVER_TOLERANCE = 1e-8
TEMPERATURE_SOLVER_MAX_ITERATIONS = 10


def solve_forest_posterior(
    forest_artifact: ForestArtifact,
    node_scores: FloatVector,
    initial_entropy: float,
    temperature_sharpening: float,
    initial_temperature: float | None = None,
) -> tuple[FloatVector, float, float, tuple[int, ...], int, float]:
    if initial_temperature is None or initial_temperature <= 0.0:
        current_temperature = 1.0
    else:
        current_temperature = initial_temperature

    marginal_probabilities: FloatVector | None = None
    current_entropy = initial_entropy
    leader_problem_type_indices: tuple[int, ...] = tuple()
    leader_state_index = _build_state_signature(leader_problem_type_indices)
    leader_state_probability = 0.0

    for iteration_index in range(TEMPERATURE_SOLVER_MAX_ITERATIONS):
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
            "Solved forest entrance assessment temperature iteration {}: temperature={}, entropy={}, next_temperature={}",
            iteration_index + 1,
            current_temperature,
            current_entropy,
            next_temperature,
        )
        if abs(next_temperature - current_temperature) <= TEMPERATURE_SOLVER_TOLERANCE:
            current_temperature = next_temperature
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
            break

        current_temperature = next_temperature

    if marginal_probabilities is None:
        raise ValueError("Forest posterior solver did not produce marginals")

    return (
        marginal_probabilities,
        current_entropy,
        current_temperature,
        leader_problem_type_indices,
        leader_state_index,
        leader_state_probability,
    )


def calculate_forest_posterior(
    forest_artifact: ForestArtifact,
    node_scores: FloatVector,
    temperature: float,
) -> tuple[FloatVector, float, tuple[int, ...], int, float]:
    include_log_weight = np.zeros(len(node_scores), dtype=np.float64)
    subtree_log_partition = np.zeros(len(node_scores), dtype=np.float64)
    best_log_weight = np.zeros(len(node_scores), dtype=np.float64)

    for node_index in forest_artifact.postorder_indices:
        child_partition_sum = sum(
            float(subtree_log_partition[child_index])
            for child_index in forest_artifact.children_by_index[node_index]
        )
        child_best_sum = sum(
            float(best_log_weight[child_index])
            for child_index in forest_artifact.children_by_index[node_index]
        )
        include_value = (temperature * float(node_scores[node_index])) + child_partition_sum
        include_log_weight[node_index] = include_value
        subtree_log_partition[node_index] = float(np.logaddexp(0.0, include_value))
        best_log_weight[node_index] = max(0.0, (temperature * float(node_scores[node_index])) + child_best_sum)

    marginal_probabilities = np.zeros(len(node_scores), dtype=np.float64)
    _fill_marginal_probabilities(
        forest_artifact=forest_artifact,
        include_log_weight=include_log_weight,
        subtree_log_partition=subtree_log_partition,
        marginal_probabilities=marginal_probabilities,
    )

    log_partition = sum(
        float(subtree_log_partition[root_index])
        for root_index in forest_artifact.root_indices
    )
    expected_score = float(np.dot(node_scores, marginal_probabilities))
    entropy = log_partition - (temperature * expected_score)

    leader_problem_type_indices = _build_map_problem_type_indices(
        forest_artifact=forest_artifact,
        include_log_weight=include_log_weight,
    )
    leader_log_weight = sum(
        float(best_log_weight[root_index])
        for root_index in forest_artifact.root_indices
    )
    leader_state_probability = float(np.exp(leader_log_weight - log_partition))
    leader_state_index = _build_state_signature(leader_problem_type_indices)

    return (
        marginal_probabilities,
        entropy,
        leader_problem_type_indices,
        leader_state_index,
        leader_state_probability,
    )


def _fill_marginal_probabilities(
    forest_artifact: ForestArtifact,
    include_log_weight: FloatVector,
    subtree_log_partition: FloatVector,
    marginal_probabilities: FloatVector,
) -> None:
    include_probability_given_parent = np.exp(
        include_log_weight - subtree_log_partition
    )

    for root_index in forest_artifact.root_indices:
        root_probability = float(include_probability_given_parent[root_index])
        marginal_probabilities[root_index] = root_probability
        _fill_child_marginals(
            forest_artifact=forest_artifact,
            include_probability_given_parent=include_probability_given_parent,
            marginal_probabilities=marginal_probabilities,
            node_index=root_index,
        )


def _fill_child_marginals(
    forest_artifact: ForestArtifact,
    include_probability_given_parent: FloatVector,
    marginal_probabilities: FloatVector,
    node_index: int,
) -> None:
    for child_index in forest_artifact.children_by_index[node_index]:
        marginal_probabilities[child_index] = (
            marginal_probabilities[node_index]
            * float(include_probability_given_parent[child_index])
        )
        _fill_child_marginals(
            forest_artifact=forest_artifact,
            include_probability_given_parent=include_probability_given_parent,
            marginal_probabilities=marginal_probabilities,
            node_index=child_index,
        )


def _build_map_problem_type_indices(
    forest_artifact: ForestArtifact,
    include_log_weight: FloatVector,
) -> tuple[int, ...]:
    leader_problem_type_indices: list[int] = []

    for root_index in forest_artifact.root_indices:
        _collect_map_problem_type_indices(
            forest_artifact=forest_artifact,
            include_log_weight=include_log_weight,
            node_index=root_index,
            parent_is_included=True,
            leader_problem_type_indices=leader_problem_type_indices,
        )

    return tuple(leader_problem_type_indices)


def _collect_map_problem_type_indices(
    forest_artifact: ForestArtifact,
    include_log_weight: FloatVector,
    node_index: int,
    parent_is_included: bool,
    leader_problem_type_indices: list[int],
) -> None:
    if not parent_is_included or float(include_log_weight[node_index]) <= 0.0:
        return

    leader_problem_type_indices.append(node_index)

    for child_index in forest_artifact.children_by_index[node_index]:
        _collect_map_problem_type_indices(
            forest_artifact=forest_artifact,
            include_log_weight=include_log_weight,
            node_index=child_index,
            parent_is_included=True,
            leader_problem_type_indices=leader_problem_type_indices,
        )


def _build_state_signature(leader_problem_type_indices: tuple[int, ...]) -> int:
    source_value = ",".join(str(node_index) for node_index in leader_problem_type_indices)
    digest = hashlib.sha1(source_value.encode("utf-8")).hexdigest()
    signature = int(digest[:12], 16) % 2_147_483_647
    return signature or 1
