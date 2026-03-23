from __future__ import annotations

from math import isclose

import numpy as np

from src.math_models.entrance_assessment.types import (
    FloatVector,
    GraphArtifact,
    Outcome,
)


def build_support_profile(
    graph_artifact: GraphArtifact,
    answered_problem_type_index: int,
    outcome: Outcome,
    i_dont_know_scalar: float,
    ancestor_support_correct: float,
    ancestor_support_wrong: float,
    descendant_support_correct: float,
    descendant_support_wrong: float,
    ancestor_decay: float,
    descendant_decay: float,
) -> FloatVector:
    node_count = len(graph_artifact.node_ids)
    support_profile = np.zeros(node_count, dtype=np.float64)

    direct_weight: float
    ancestor_weight: float
    descendant_weight: float

    if outcome == Outcome.CORRECT:
        direct_weight = 1.0
        ancestor_weight = float(ancestor_support_correct)
        descendant_weight = float(descendant_support_correct)
    elif outcome == Outcome.INCORRECT:
        direct_weight = -1.0
        ancestor_weight = -float(ancestor_support_wrong)
        descendant_weight = -float(descendant_support_wrong)
    else:
        scale = float(i_dont_know_scalar)
        direct_weight = -scale
        ancestor_weight = -float(ancestor_support_wrong) * scale
        descendant_weight = -float(descendant_support_wrong) * scale

    support_profile[answered_problem_type_index] = direct_weight

    _add_normalized_support(
        support_profile=support_profile,
        target_indices=graph_artifact.ancestors_by_index[answered_problem_type_index],
        distances=graph_artifact.ancestor_distances_to_index[
            answered_problem_type_index
        ],
        branch_support={},
        coefficient=ancestor_weight,
        decay=float(ancestor_decay),
        epsilon=1e-12,
    )
    _add_normalized_support(
        support_profile=support_profile,
        target_indices=graph_artifact.descendants_by_index[
            answered_problem_type_index
        ],
        distances=graph_artifact.descendant_distances_from_index[
            answered_problem_type_index
        ],
        branch_support=graph_artifact.descendant_branch_support_from_index[
            answered_problem_type_index
        ],
        coefficient=descendant_weight,
        decay=float(descendant_decay),
        epsilon=1e-12,
    )

    return support_profile


def _add_normalized_support(
    support_profile: FloatVector,
    target_indices: tuple[int, ...],
    distances: dict[int, int],
    branch_support: dict[int, float],
    coefficient: float,
    decay: float,
    epsilon: float,
) -> None:
    if not target_indices or isclose(coefficient, 0.0, abs_tol=epsilon):
        return

    raw_values: list[float] = []
    total_raw_value = 0.0

    for target_index in target_indices:
        distance = max(distances[target_index], 1)
        distance_weight = decay ** (distance - 1)
        branch_weight = branch_support.get(target_index, 1.0)
        raw_value = distance_weight * branch_weight
        raw_values.append(raw_value)
        total_raw_value += raw_value

    if total_raw_value <= epsilon:
        return

    normalized_scale = coefficient / total_raw_value

    for target_index, raw_value in zip(target_indices, raw_values, strict=True):
        support_profile[target_index] += raw_value * normalized_scale
