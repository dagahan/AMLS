from __future__ import annotations

import numpy as np

from src.math_models.entrance_assessment.types import (
    GraphArtifact,
    RuntimeSnapshot,
    SelectionResult,
    StateArtifact,
)


def select_next_problem_type(
    graph_artifact: GraphArtifact,
    state_artifact: StateArtifact,
    runtime: RuntimeSnapshot,
    available_problem_type_indices: set[int] | None = None,
) -> SelectionResult:
    node_count = len(graph_artifact.node_ids)
    marginals = np.zeros(node_count, dtype=np.float64)
    utilities = np.zeros(node_count, dtype=np.float64)
    asked_indices = set(runtime.asked_problem_type_indices)

    for node_index in range(node_count):
        if node_index in asked_indices:
            continue
        if available_problem_type_indices is not None and node_index not in available_problem_type_indices:
            continue

        containing_state_indices = state_artifact.states_containing_node_indices[node_index]
        marginal_probability = float(runtime.probabilities[containing_state_indices].sum())
        utility = 4.0 * marginal_probability * (1.0 - marginal_probability)

        marginals[node_index] = marginal_probability
        utilities[node_index] = utility

    candidate_indices = [
        node_index
        for node_index in range(node_count)
        if node_index not in asked_indices
        and (available_problem_type_indices is None or node_index in available_problem_type_indices)
    ]

    if not candidate_indices:
        return SelectionResult(
            problem_type_index=None,
            problem_type_id=None,
            marginal_probabilities=marginals,
            utilities=utilities,
            max_utility=0.0,
        )

    best_index = max(candidate_indices, key=lambda node_index: float(utilities[node_index]))
    best_utility = float(utilities[best_index])

    return SelectionResult(
        problem_type_index=best_index,
        problem_type_id=graph_artifact.node_ids[best_index],
        marginal_probabilities=marginals,
        utilities=utilities,
        max_utility=best_utility,
    )
