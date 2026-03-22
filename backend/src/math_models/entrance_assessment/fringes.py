from __future__ import annotations

from src.math_models.entrance_assessment.types import GraphArtifact


def compute_inner_fringe_indices(
    graph_artifact: GraphArtifact,
    learned_problem_type_indices: tuple[int, ...],
) -> tuple[int, ...]:
    learned_index_set = set(learned_problem_type_indices)
    inner_fringe_indices = [
        node_index
        for node_index in learned_problem_type_indices
        if all(
            child_index not in learned_index_set
            for child_index in graph_artifact.dependents_by_index[node_index]
        )
    ]
    return tuple(sorted(inner_fringe_indices))


def compute_outer_fringe_indices(
    graph_artifact: GraphArtifact,
    learned_problem_type_indices: tuple[int, ...],
) -> tuple[int, ...]:
    learned_index_set = set(learned_problem_type_indices)
    outer_fringe_indices = [
        node_index
        for node_index in range(len(graph_artifact.node_ids))
        if node_index not in learned_index_set
        and all(
            prerequisite_index in learned_index_set
            for prerequisite_index in graph_artifact.prerequisites_by_index[node_index]
        )
    ]
    return tuple(sorted(outer_fringe_indices))
