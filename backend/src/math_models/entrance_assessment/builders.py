from __future__ import annotations

import math
import uuid
from collections import deque

import numpy as np
from loguru import logger

from src.models.pydantic import ForestArtifact, GraphArtifact


class ForestStructureError(RuntimeError):
    pass


def build_graph_artifact(
    problem_type_ids: tuple[uuid.UUID, ...],
    prerequisite_edges: tuple[tuple[uuid.UUID, uuid.UUID], ...],
) -> GraphArtifact:
    ordered_problem_type_ids = tuple(problem_type_ids)
    index_by_id = {
        problem_type_id: index
        for index, problem_type_id in enumerate(ordered_problem_type_ids)
    }
    node_count = len(ordered_problem_type_ids)
    prerequisites_by_index: list[list[int]] = [[] for _ in range(node_count)]
    dependents_by_index: list[list[int]] = [[] for _ in range(node_count)]

    for problem_type_id, prerequisite_problem_type_id in prerequisite_edges:
        problem_type_index = index_by_id[problem_type_id]
        prerequisite_index = index_by_id[prerequisite_problem_type_id]
        prerequisites_by_index[problem_type_index].append(prerequisite_index)
        dependents_by_index[prerequisite_index].append(problem_type_index)

    normalized_prerequisites = tuple(
        tuple(sorted(indices))
        for indices in prerequisites_by_index
    )
    normalized_dependents = tuple(
        tuple(sorted(indices))
        for indices in dependents_by_index
    )
    indegree_by_index = np.asarray(
        [len(indices) for indices in normalized_prerequisites],
        dtype=np.int64,
    )
    topological_order = _build_topological_order(
        normalized_prerequisites,
        normalized_dependents,
    )

    logger.info(
        "Built entrance assessment graph artifact: node_count={}, edge_count={}, root_count={}",
        node_count,
        len(prerequisite_edges),
        sum(1 for indegree in indegree_by_index if indegree == 0),
    )

    return GraphArtifact(
        node_ids=ordered_problem_type_ids,
        index_by_id=index_by_id,
        prerequisites_by_index=normalized_prerequisites,
        dependents_by_index=normalized_dependents,
        indegree_by_index=indegree_by_index,
        topological_order=topological_order,
    )


def build_forest_artifact(graph_artifact: GraphArtifact) -> ForestArtifact:
    if np.any(graph_artifact.indegree_by_index > 1):
        invalid_indices = [
            index
            for index, indegree in enumerate(graph_artifact.indegree_by_index.tolist())
            if indegree > 1
        ]
        raise ForestStructureError(
            "Entrance assessment exact Bayesian engine requires a forest, "
            f"but found nodes with multiple prerequisites: {invalid_indices}"
        )

    node_count = len(graph_artifact.node_ids)
    parent_by_index = tuple(
        prerequisites[0] if prerequisites else None
        for prerequisites in graph_artifact.prerequisites_by_index
    )
    children_by_index = graph_artifact.dependents_by_index
    root_indices = tuple(
        index
        for index, parent_index in enumerate(parent_by_index)
        if parent_index is None
    )
    preorder_indices, postorder_indices, depth_by_index = _build_forest_orders(
        children_by_index=children_by_index,
        root_indices=root_indices,
        node_count=node_count,
    )
    component_sizes = tuple(
        _count_subtree_nodes(children_by_index, root_index)
        for root_index in root_indices
    )
    max_depth = max(depth_by_index, default=0)
    feasible_state_count = _build_feasible_state_count(
        children_by_index=children_by_index,
        postorder_indices=postorder_indices,
        root_indices=root_indices,
    )
    initial_entropy = math.log(feasible_state_count)

    logger.info(
        "Built entrance assessment forest artifact: node_count={}, root_count={}, max_depth={}, feasible_state_count={}",
        node_count,
        len(root_indices),
        max_depth,
        feasible_state_count,
    )

    return ForestArtifact(
        parent_by_index=parent_by_index,
        children_by_index=children_by_index,
        root_indices=root_indices,
        preorder_indices=preorder_indices,
        postorder_indices=postorder_indices,
        depth_by_index=depth_by_index,
        component_sizes=component_sizes,
        max_depth=max_depth,
        feasible_state_count=feasible_state_count,
        initial_entropy=initial_entropy,
    )


def _build_topological_order(
    prerequisites_by_index: tuple[tuple[int, ...], ...],
    dependents_by_index: tuple[tuple[int, ...], ...],
) -> tuple[int, ...]:
    pending_indegree = [len(prerequisites) for prerequisites in prerequisites_by_index]
    queue: deque[int] = deque(
        index
        for index, indegree in enumerate(pending_indegree)
        if indegree == 0
    )
    ordered_indices: list[int] = []

    while queue:
        current_index = queue.popleft()
        ordered_indices.append(current_index)

        for dependent_index in dependents_by_index[current_index]:
            pending_indegree[dependent_index] -= 1
            if pending_indegree[dependent_index] == 0:
                queue.append(dependent_index)

    if len(ordered_indices) != len(prerequisites_by_index):
        raise ForestStructureError(
            "Entrance assessment prerequisite graph contains a cycle"
        )

    return tuple(ordered_indices)


def _build_forest_orders(
    children_by_index: tuple[tuple[int, ...], ...],
    root_indices: tuple[int, ...],
    node_count: int,
) -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
    preorder_indices: list[int] = []
    postorder_indices: list[int] = []
    depth_by_index = [0] * node_count

    def visit_node(node_index: int, depth: int) -> None:
        depth_by_index[node_index] = depth
        preorder_indices.append(node_index)

        for child_index in children_by_index[node_index]:
            visit_node(child_index, depth + 1)

        postorder_indices.append(node_index)

    for root_index in root_indices:
        visit_node(root_index, 0)

    return (
        tuple(preorder_indices),
        tuple(postorder_indices),
        tuple(depth_by_index),
    )


def _count_subtree_nodes(
    children_by_index: tuple[tuple[int, ...], ...],
    node_index: int,
) -> int:
    return 1 + sum(
        _count_subtree_nodes(children_by_index, child_index)
        for child_index in children_by_index[node_index]
    )


def _build_feasible_state_count(
    children_by_index: tuple[tuple[int, ...], ...],
    postorder_indices: tuple[int, ...],
    root_indices: tuple[int, ...],
) -> int:
    subtree_state_count_by_index: dict[int, int] = {}

    for node_index in postorder_indices:
        child_state_product = 1

        for child_index in children_by_index[node_index]:
            child_state_product *= subtree_state_count_by_index[child_index]

        subtree_state_count_by_index[node_index] = 1 + child_state_product

    feasible_state_count = 1
    for root_index in root_indices:
        feasible_state_count *= subtree_state_count_by_index[root_index]

    return feasible_state_count
