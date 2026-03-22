from __future__ import annotations

from math import log

from src.math_models.entrance_assessment.types import ForestArtifact, GraphArtifact


class ForestStructureError(RuntimeError):
    pass


def build_forest_artifact(graph_artifact: GraphArtifact) -> ForestArtifact:
    node_count = len(graph_artifact.node_ids)
    parent_by_index: list[int | None] = []

    for node_index, prerequisite_indices in enumerate(
        graph_artifact.prerequisites_by_index
    ):
        if len(prerequisite_indices) > 1:
            raise ForestStructureError(
                "Entrance test structure must be a forest with at most one prerequisite per problem type"
            )

        parent_by_index.append(
            prerequisite_indices[0] if prerequisite_indices else None
        )

    root_indices = tuple(
        node_index
        for node_index, parent_index in enumerate(parent_by_index)
        if parent_index is None
    )
    children_by_index = tuple(
        tuple(child_indices)
        for child_indices in graph_artifact.dependents_by_index
    )
    preorder_indices = tuple(graph_artifact.topological_order)
    postorder_indices = tuple(reversed(graph_artifact.topological_order))
    depth_by_index = _build_depths(parent_by_index, preorder_indices)
    component_sizes = _build_component_sizes(
        children_by_index=children_by_index,
        postorder_indices=postorder_indices,
        root_indices=root_indices,
    )
    feasible_state_count = _count_feasible_states(
        children_by_index=children_by_index,
        postorder_indices=postorder_indices,
        root_indices=root_indices,
    )

    return ForestArtifact(
        parent_by_index=tuple(parent_by_index),
        children_by_index=children_by_index,
        root_indices=root_indices,
        preorder_indices=preorder_indices,
        postorder_indices=postorder_indices,
        depth_by_index=tuple(depth_by_index),
        component_sizes=component_sizes,
        max_depth=max(depth_by_index, default=0),
        feasible_state_count=feasible_state_count,
        initial_entropy=log(feasible_state_count) if feasible_state_count > 0 else 0.0,
    )


def _build_depths(
    parent_by_index: list[int | None],
    preorder_indices: tuple[int, ...],
) -> list[int]:
    depths = [0] * len(parent_by_index)

    for node_index in preorder_indices:
        parent_index = parent_by_index[node_index]
        if parent_index is None:
            depths[node_index] = 0
            continue

        depths[node_index] = depths[parent_index] + 1

    return depths


def _build_component_sizes(
    children_by_index: tuple[tuple[int, ...], ...],
    postorder_indices: tuple[int, ...],
    root_indices: tuple[int, ...],
) -> tuple[int, ...]:
    subtree_sizes = [1] * len(children_by_index)

    for node_index in postorder_indices:
        subtree_sizes[node_index] = 1 + sum(
            subtree_sizes[child_index]
            for child_index in children_by_index[node_index]
        )

    return tuple(subtree_sizes[root_index] for root_index in root_indices)


def _count_feasible_states(
    children_by_index: tuple[tuple[int, ...], ...],
    postorder_indices: tuple[int, ...],
    root_indices: tuple[int, ...],
) -> int:
    subtree_state_counts = [1] * len(children_by_index)

    for node_index in postorder_indices:
        child_product = 1
        for child_index in children_by_index[node_index]:
            child_product *= subtree_state_counts[child_index]

        subtree_state_counts[node_index] = 1 + child_product

    total_state_count = 1
    for root_index in root_indices:
        total_state_count *= subtree_state_counts[root_index]

    return total_state_count
