from __future__ import annotations

from collections import deque
from time import perf_counter
import uuid

from loguru import logger
import numpy as np

from src.math_models.entrance_assessment.types import GraphArtifact, IntVector


def build_graph_artifact(
    problem_type_ids: tuple[uuid.UUID, ...],
    prerequisite_edges: tuple[tuple[uuid.UUID, uuid.UUID], ...],
    branch_penalty_exponent: float,
) -> GraphArtifact:
    started_at = perf_counter()
    node_ids = tuple(problem_type_ids)
    index_by_id = {
        problem_type_id: index
        for index, problem_type_id in enumerate(node_ids)
    }
    node_count = len(node_ids)
    prerequisites_lists: list[list[int]] = [[] for _ in range(node_count)]
    dependents_lists: list[list[int]] = [[] for _ in range(node_count)]

    for problem_type_id, prerequisite_problem_type_id in prerequisite_edges:
        child_index = index_by_id[problem_type_id]
        parent_index = index_by_id[prerequisite_problem_type_id]
        prerequisites_lists[child_index].append(parent_index)
        dependents_lists[parent_index].append(child_index)

    prerequisites_by_index = tuple(
        tuple(sorted(indices))
        for indices in prerequisites_lists
    )
    dependents_by_index = tuple(
        tuple(sorted(indices))
        for indices in dependents_lists
    )
    indegree_by_index = np.asarray(
        [len(indices) for indices in prerequisites_by_index],
        dtype=np.int64,
    )
    topological_order = _build_topological_order(
        prerequisites_by_index=prerequisites_by_index,
        dependents_by_index=dependents_by_index,
        indegree_by_index=indegree_by_index,
        node_ids=node_ids,
    )
    ancestors_by_index, ancestor_distances_to_index = _build_ancestor_maps(
        prerequisites_by_index=prerequisites_by_index,
        topological_order=topological_order,
    )
    descendants_by_index, descendant_distances_from_index = _build_descendant_maps(
        dependents_by_index=dependents_by_index,
        topological_order=topological_order,
    )
    descendant_branch_support_from_index = _build_descendant_branch_support(
        dependents_by_index=dependents_by_index,
        topological_order=topological_order,
        branch_penalty_exponent=branch_penalty_exponent,
    )
    elapsed_ms = (perf_counter() - started_at) * 1000

    logger.info(
        "Built graph artifact: node_count={}, edge_count={}, branch_penalty_exponent={}, elapsed_ms={:.3f}",
        node_count,
        len(prerequisite_edges),
        branch_penalty_exponent,
        elapsed_ms,
    )

    return GraphArtifact(
        node_ids=node_ids,
        index_by_id=index_by_id,
        prerequisites_by_index=prerequisites_by_index,
        dependents_by_index=dependents_by_index,
        indegree_by_index=indegree_by_index,
        topological_order=topological_order,
        ancestors_by_index=ancestors_by_index,
        descendants_by_index=descendants_by_index,
        ancestor_distances_to_index=ancestor_distances_to_index,
        descendant_distances_from_index=descendant_distances_from_index,
        descendant_branch_support_from_index=descendant_branch_support_from_index,
    )


def _build_topological_order(
    prerequisites_by_index: tuple[tuple[int, ...], ...],
    dependents_by_index: tuple[tuple[int, ...], ...],
    indegree_by_index: IntVector,
    node_ids: tuple[uuid.UUID, ...],
) -> tuple[int, ...]:
    queue = deque(
        index
        for index, indegree in enumerate(indegree_by_index)
        if indegree == 0
    )
    remaining_indegree = indegree_by_index.copy()
    topological_order: list[int] = []

    while queue:
        current_index = queue.popleft()
        topological_order.append(current_index)

        for dependent_index in dependents_by_index[current_index]:
            remaining_indegree[dependent_index] -= 1
            if remaining_indegree[dependent_index] == 0:
                queue.append(dependent_index)

    if len(topological_order) != len(node_ids):
        raise ValueError("Problem type graph must be acyclic")

    logger.debug(
        "Built topological order: node_count={}, first_indices={}, last_indices={}",
        len(topological_order),
        topological_order[:5],
        topological_order[-5:],
    )
    return tuple(topological_order)


def _build_ancestor_maps(
    prerequisites_by_index: tuple[tuple[int, ...], ...],
    topological_order: tuple[int, ...],
) -> tuple[tuple[tuple[int, ...], ...], tuple[dict[int, int], ...]]:
    node_count = len(prerequisites_by_index)
    ancestors_by_index: list[tuple[int, ...]] = [tuple() for _ in range(node_count)]
    ancestor_distances_to_index: list[dict[int, int]] = [
        {}
        for _ in range(node_count)
    ]

    for node_index in topological_order:
        ancestor_distances: dict[int, int] = {}

        for prerequisite_index in prerequisites_by_index[node_index]:
            ancestor_distances[prerequisite_index] = 1

            for ancestor_index, distance in ancestor_distances_to_index[
                prerequisite_index
            ].items():
                candidate_distance = distance + 1
                previous_distance = ancestor_distances.get(ancestor_index)
                if previous_distance is None or candidate_distance < previous_distance:
                    ancestor_distances[ancestor_index] = candidate_distance

        ordered_ancestors = tuple(
            sorted(
                ancestor_distances,
                key=lambda index: (ancestor_distances[index], index),
            )
        )
        ancestors_by_index[node_index] = ordered_ancestors
        ancestor_distances_to_index[node_index] = ancestor_distances

    return tuple(ancestors_by_index), tuple(ancestor_distances_to_index)


def _build_descendant_maps(
    dependents_by_index: tuple[tuple[int, ...], ...],
    topological_order: tuple[int, ...],
) -> tuple[tuple[tuple[int, ...], ...], tuple[dict[int, int], ...]]:
    node_count = len(dependents_by_index)
    descendants_by_index: list[tuple[int, ...]] = [tuple() for _ in range(node_count)]
    descendant_distances_from_index: list[dict[int, int]] = [
        {}
        for _ in range(node_count)
    ]

    for node_index in reversed(topological_order):
        descendant_distances: dict[int, int] = {}

        for dependent_index in dependents_by_index[node_index]:
            descendant_distances[dependent_index] = 1

            for descendant_index, distance in descendant_distances_from_index[
                dependent_index
            ].items():
                candidate_distance = distance + 1
                previous_distance = descendant_distances.get(descendant_index)
                if previous_distance is None or candidate_distance < previous_distance:
                    descendant_distances[descendant_index] = candidate_distance

        ordered_descendants = tuple(
            sorted(
                descendant_distances,
                key=lambda index: (descendant_distances[index], index),
            )
        )
        descendants_by_index[node_index] = ordered_descendants
        descendant_distances_from_index[node_index] = descendant_distances

    return tuple(descendants_by_index), tuple(descendant_distances_from_index)


def _build_descendant_branch_support(
    dependents_by_index: tuple[tuple[int, ...], ...],
    topological_order: tuple[int, ...],
    branch_penalty_exponent: float,
) -> tuple[dict[int, float], ...]:
    node_count = len(dependents_by_index)
    descendant_branch_support_from_index: list[dict[int, float]] = [
        {}
        for _ in range(node_count)
    ]

    for node_index in reversed(topological_order):
        branch_support_by_descendant: dict[int, float] = {}
        child_count = max(len(dependents_by_index[node_index]), 1)

        for dependent_index in dependents_by_index[node_index]:
            local_branch_factor = 1.0 / (child_count ** branch_penalty_exponent)
            branch_support_by_descendant[dependent_index] = local_branch_factor

            for descendant_index, branch_support in descendant_branch_support_from_index[
                dependent_index
            ].items():
                branch_support_by_descendant[descendant_index] = (
                    local_branch_factor * branch_support
                )

        descendant_branch_support_from_index[node_index] = branch_support_by_descendant

    logger.debug(
        "Built descendant branch support maps: node_count={}, avg_descendants={:.3f}",
        node_count,
        sum(
            len(branch_support)
            for branch_support in descendant_branch_support_from_index
        )
        / max(node_count, 1),
    )
    return tuple(descendant_branch_support_from_index)
