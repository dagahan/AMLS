from __future__ import annotations

from collections import deque
from math import inf
import uuid

import numpy as np

from src.math_models.entrance_assessment.types import GraphArtifact, IntVector


def build_graph_artifact(
    problem_type_ids: tuple[uuid.UUID, ...],
    prerequisite_edges: tuple[tuple[uuid.UUID, uuid.UUID], ...],
    branch_penalty_exponent: float,
) -> GraphArtifact:
    node_ids = tuple(problem_type_ids)
    index_by_id = {problem_type_id: index for index, problem_type_id in enumerate(node_ids)}
    node_count = len(node_ids)

    prerequisites: list[set[int]] = [set() for _ in range(node_count)]
    dependents: list[set[int]] = [set() for _ in range(node_count)]

    for problem_type_id, prerequisite_problem_type_id in prerequisite_edges:
        child_index = index_by_id[problem_type_id]
        parent_index = index_by_id[prerequisite_problem_type_id]
        prerequisites[child_index].add(parent_index)
        dependents[parent_index].add(child_index)

    topological_order = _build_topological_order(node_count, prerequisites, dependents)
    ancestors_by_index = _build_ancestors_by_index(prerequisites, topological_order)
    descendants_by_index = _build_descendants_by_index(dependents, topological_order)
    ancestor_distances_to_index = tuple(
        _build_reverse_distances(start_index=index, prerequisites=prerequisites)
        for index in range(node_count)
    )
    descendant_distances_from_index = tuple(
        _build_forward_distances(start_index=index, dependents=dependents)
        for index in range(node_count)
    )
    indegree_by_index = np.asarray(
        [len(prerequisite_indices) for prerequisite_indices in prerequisites],
        dtype=np.int64,
    )
    descendant_branch_support_from_index = tuple(
        _build_descendant_branch_support(
            start_index=index,
            dependents=dependents,
            indegree_by_index=indegree_by_index,
            topological_order=topological_order,
            branch_penalty_exponent=branch_penalty_exponent,
        )
        for index in range(node_count)
    )

    return GraphArtifact(
        node_ids=node_ids,
        index_by_id=index_by_id,
        prerequisites_by_index=tuple(
            tuple(sorted(prerequisite_indices))
            for prerequisite_indices in prerequisites
        ),
        dependents_by_index=tuple(
            tuple(sorted(dependent_indices))
            for dependent_indices in dependents
        ),
        indegree_by_index=indegree_by_index,
        topological_order=topological_order,
        ancestors_by_index=tuple(
            tuple(sorted(ancestor_indices))
            for ancestor_indices in ancestors_by_index
        ),
        descendants_by_index=tuple(
            tuple(sorted(descendant_indices))
            for descendant_indices in descendants_by_index
        ),
        ancestor_distances_to_index=ancestor_distances_to_index,
        descendant_distances_from_index=descendant_distances_from_index,
        descendant_branch_support_from_index=descendant_branch_support_from_index,
    )


def _build_topological_order(
    node_count: int,
    prerequisites: list[set[int]],
    dependents: list[set[int]],
) -> tuple[int, ...]:
    in_degree = [len(prerequisite_indices) for prerequisite_indices in prerequisites]
    queue = deque(sorted(index for index in range(node_count) if in_degree[index] == 0))
    order: list[int] = []

    while queue:
        current_index = queue.popleft()
        order.append(current_index)

        for dependent_index in sorted(dependents[current_index]):
            in_degree[dependent_index] -= 1
            if in_degree[dependent_index] == 0:
                queue.append(dependent_index)

    if len(order) != node_count:
        raise ValueError("Problem type graph must be acyclic")

    return tuple(order)


def _build_ancestors_by_index(
    prerequisites: list[set[int]],
    topological_order: tuple[int, ...],
) -> tuple[set[int], ...]:
    ancestors: list[set[int]] = [set() for _ in range(len(prerequisites))]

    for node_index in topological_order:
        for parent_index in prerequisites[node_index]:
            ancestors[node_index].add(parent_index)
            ancestors[node_index].update(ancestors[parent_index])

    return tuple(ancestors)


def _build_descendants_by_index(
    dependents: list[set[int]],
    topological_order: tuple[int, ...],
) -> tuple[set[int], ...]:
    descendants: list[set[int]] = [set() for _ in range(len(dependents))]

    for node_index in reversed(topological_order):
        for child_index in dependents[node_index]:
            descendants[node_index].add(child_index)
            descendants[node_index].update(descendants[child_index])

    return tuple(descendants)


def _build_reverse_distances(
    start_index: int,
    prerequisites: list[set[int]],
) -> dict[int, int]:
    distances: dict[int, int] = {}
    queue = deque([(start_index, 0)])

    while queue:
        current_index, current_distance = queue.popleft()
        for parent_index in prerequisites[current_index]:
            if parent_index in distances:
                continue
            next_distance = current_distance + 1
            distances[parent_index] = next_distance
            queue.append((parent_index, next_distance))

    return distances


def _build_forward_distances(
    start_index: int,
    dependents: list[set[int]],
) -> dict[int, int]:
    distances: dict[int, int] = {}
    queue = deque([(start_index, 0)])

    while queue:
        current_index, current_distance = queue.popleft()
        for child_index in dependents[current_index]:
            if child_index in distances:
                continue
            next_distance = current_distance + 1
            distances[child_index] = next_distance
            queue.append((child_index, next_distance))

    return distances


def _build_descendant_branch_support(
    start_index: int,
    dependents: list[set[int]],
    indegree_by_index: IntVector,
    topological_order: tuple[int, ...],
    branch_penalty_exponent: float,
) -> dict[int, float]:
    support_by_index: dict[int, float] = {}

    for node_index in topological_order:
        if node_index == start_index:
            base_support = 1.0
        else:
            base_support = support_by_index.get(node_index, 0.0)
            if base_support <= 0.0:
                continue

        for child_index in dependents[node_index]:
            child_in_degree = int(indegree_by_index[child_index])
            penalty = 1.0
            if child_in_degree > 0:
                penalty = 1.0 / (float(child_in_degree) ** branch_penalty_exponent)

            candidate_support = base_support * penalty
            current_support = support_by_index.get(child_index, -inf)
            if candidate_support > current_support:
                support_by_index[child_index] = candidate_support

    support_by_index.pop(start_index, None)
    return support_by_index
