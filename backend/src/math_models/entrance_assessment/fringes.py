from __future__ import annotations

from src.math_models.entrance_assessment.types import GraphArtifact, StateArtifact


def extract_problem_type_indices_from_mask(state_mask: int) -> tuple[int, ...]:
    indices: list[int] = []
    remaining_mask = state_mask

    while remaining_mask:
        least_significant_bit = remaining_mask & -remaining_mask
        node_index = least_significant_bit.bit_length() - 1
        indices.append(node_index)
        remaining_mask ^= least_significant_bit

    return tuple(indices)


def compute_inner_fringe_indices(
    state_artifact: StateArtifact,
    state_mask: int,
) -> tuple[int, ...]:
    inner_fringe: list[int] = []

    for node_index in extract_problem_type_indices_from_mask(state_mask):
        predecessor_mask = state_mask & ~(1 << node_index)
        if predecessor_mask in state_artifact.state_index_by_mask:
            inner_fringe.append(node_index)

    return tuple(sorted(inner_fringe))


def compute_outer_fringe_indices(
    graph_artifact: GraphArtifact,
    state_artifact: StateArtifact,
    state_mask: int,
) -> tuple[int, ...]:
    outer_fringe: list[int] = []
    node_count = len(graph_artifact.node_ids)

    for node_index in range(node_count):
        node_bit = 1 << node_index
        if state_mask & node_bit:
            continue

        successor_mask = state_mask | node_bit
        if successor_mask in state_artifact.state_index_by_mask:
            outer_fringe.append(node_index)

    return tuple(sorted(outer_fringe))
