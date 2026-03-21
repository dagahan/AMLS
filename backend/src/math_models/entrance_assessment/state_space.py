from __future__ import annotations

from math import log2

import numpy as np

from src.math_models.entrance_assessment.types import GraphArtifact, IntVector, Int8Matrix, StateArtifact


def build_state_artifact(graph_artifact: GraphArtifact) -> StateArtifact:
    prerequisite_masks = _build_prerequisite_masks(graph_artifact)
    state_masks = _generate_feasible_states(graph_artifact, prerequisite_masks)
    state_index_by_mask = {
        state_mask: state_index
        for state_index, state_mask in enumerate(state_masks)
    }
    state_sign_matrix = _build_state_sign_matrix(
        state_masks=state_masks,
        node_count=len(graph_artifact.node_ids),
    )
    states_containing_node_indices = _build_states_containing_node_indices(
        state_masks=state_masks,
        node_count=len(graph_artifact.node_ids),
    )
    initial_entropy = log2(len(state_masks)) if state_masks else 0.0

    return StateArtifact(
        state_masks=state_masks,
        state_index_by_mask=state_index_by_mask,
        state_sign_matrix=state_sign_matrix,
        states_containing_node_indices=states_containing_node_indices,
        initial_entropy=initial_entropy,
    )


def _build_prerequisite_masks(graph_artifact: GraphArtifact) -> tuple[int, ...]:
    masks: list[int] = []

    for prerequisite_indices in graph_artifact.prerequisites_by_index:
        mask = 0
        for prerequisite_index in prerequisite_indices:
            mask |= 1 << prerequisite_index
        masks.append(mask)

    return tuple(masks)


def _generate_feasible_states(
    graph_artifact: GraphArtifact,
    prerequisite_masks: tuple[int, ...],
) -> tuple[int, ...]:
    states: set[int] = {0}

    for node_index in graph_artifact.topological_order:
        node_bit = 1 << node_index
        prerequisite_mask = prerequisite_masks[node_index]
        next_states = set(states)

        for state_mask in states:
            if state_mask & prerequisite_mask == prerequisite_mask:
                next_states.add(state_mask | node_bit)

        states = next_states

    return tuple(sorted(states, key=lambda state_mask: (state_mask.bit_count(), state_mask)))


def _build_state_sign_matrix(
    state_masks: tuple[int, ...],
    node_count: int,
) -> Int8Matrix:
    matrix = np.full((len(state_masks), node_count), -1, dtype=np.int8)

    for state_index, state_mask in enumerate(state_masks):
        remaining_mask = state_mask
        while remaining_mask:
            least_significant_bit = remaining_mask & -remaining_mask
            node_index = least_significant_bit.bit_length() - 1
            matrix[state_index, node_index] = 1
            remaining_mask ^= least_significant_bit

    return matrix


def _build_states_containing_node_indices(
    state_masks: tuple[int, ...],
    node_count: int,
) -> tuple[IntVector, ...]:
    state_indices_by_node: list[list[int]] = [[] for _ in range(node_count)]

    for state_index, state_mask in enumerate(state_masks):
        remaining_mask = state_mask
        while remaining_mask:
            least_significant_bit = remaining_mask & -remaining_mask
            node_index = least_significant_bit.bit_length() - 1
            state_indices_by_node[node_index].append(state_index)
            remaining_mask ^= least_significant_bit

    return tuple(
        np.asarray(state_indices, dtype=np.int64)
        for state_indices in state_indices_by_node
    )
