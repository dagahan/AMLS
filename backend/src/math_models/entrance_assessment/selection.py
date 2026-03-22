from __future__ import annotations

import numpy as np

from src.math_models.entrance_assessment.types import (
    GraphArtifact,
    RuntimeSnapshot,
    SelectionResult,
)


def select_next_problem_type(
    graph_artifact: GraphArtifact,
    runtime: RuntimeSnapshot,
    available_problem_type_indices: set[int] | None = None,
) -> SelectionResult:
    node_count = len(graph_artifact.node_ids)
    utilities = np.zeros(node_count, dtype=np.float64)
    marginal_probabilities = np.asarray(
        runtime.marginal_probabilities,
        dtype=np.float64,
    )
    asked_indices = set(runtime.asked_problem_type_indices)

    candidate_indices = [
        node_index
        for node_index in range(node_count)
        if node_index not in asked_indices
        and (
            available_problem_type_indices is None
            or node_index in available_problem_type_indices
        )
    ]

    for node_index in candidate_indices:
        marginal_probability = float(marginal_probabilities[node_index])
        utilities[node_index] = 4.0 * marginal_probability * (1.0 - marginal_probability)

    if not candidate_indices:
        return SelectionResult(
            problem_type_index=None,
            problem_type_id=None,
            marginal_probabilities=marginal_probabilities,
            utilities=utilities,
            max_utility=0.0,
        )

    best_index = max(
        candidate_indices,
        key=lambda node_index: float(utilities[node_index]),
    )
    best_utility = float(utilities[best_index])

    return SelectionResult(
        problem_type_index=best_index,
        problem_type_id=graph_artifact.node_ids[best_index],
        marginal_probabilities=marginal_probabilities,
        utilities=utilities,
        max_utility=best_utility,
    )
