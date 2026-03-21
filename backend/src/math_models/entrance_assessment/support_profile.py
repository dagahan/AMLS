from __future__ import annotations

from math import exp

import numpy as np

from src.math_models.entrance_assessment.types import FloatVector, GraphArtifact, Outcome


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
    profile = np.zeros(node_count, dtype=np.float64)

    if outcome == Outcome.CORRECT:
        _apply_correct_profile(
            graph_artifact=graph_artifact,
            answered_problem_type_index=answered_problem_type_index,
            profile=profile,
            ancestor_support_correct=ancestor_support_correct,
            descendant_support_correct=descendant_support_correct,
            ancestor_decay=ancestor_decay,
            descendant_decay=descendant_decay,
        )
        return profile

    _apply_incorrect_profile(
        graph_artifact=graph_artifact,
        answered_problem_type_index=answered_problem_type_index,
        profile=profile,
        ancestor_support_wrong=ancestor_support_wrong,
        descendant_support_wrong=descendant_support_wrong,
        ancestor_decay=ancestor_decay,
        descendant_decay=descendant_decay,
    )

    if outcome == Outcome.I_DONT_KNOW:
        profile *= i_dont_know_scalar

    return profile


def _apply_correct_profile(
    graph_artifact: GraphArtifact,
    answered_problem_type_index: int,
    profile: FloatVector,
    ancestor_support_correct: float,
    descendant_support_correct: float,
    ancestor_decay: float,
    descendant_decay: float,
) -> None:
    profile[answered_problem_type_index] = 1.0

    for ancestor_index, distance in graph_artifact.ancestor_distances_to_index[
        answered_problem_type_index
    ].items():
        profile[ancestor_index] = ancestor_support_correct * exp(
            -ancestor_decay * float(distance)
        )

    for descendant_index, distance in graph_artifact.descendant_distances_from_index[
        answered_problem_type_index
    ].items():
        branch_support = graph_artifact.descendant_branch_support_from_index[
            answered_problem_type_index
        ].get(descendant_index, 0.0)
        profile[descendant_index] = descendant_support_correct * exp(
            -descendant_decay * float(distance)
        ) * branch_support


def _apply_incorrect_profile(
    graph_artifact: GraphArtifact,
    answered_problem_type_index: int,
    profile: FloatVector,
    ancestor_support_wrong: float,
    descendant_support_wrong: float,
    ancestor_decay: float,
    descendant_decay: float,
) -> None:
    profile[answered_problem_type_index] = -1.0

    for ancestor_index, distance in graph_artifact.ancestor_distances_to_index[
        answered_problem_type_index
    ].items():
        profile[ancestor_index] = -(ancestor_support_wrong * exp(-ancestor_decay * float(distance)))

    for descendant_index, distance in graph_artifact.descendant_distances_from_index[
        answered_problem_type_index
    ].items():
        branch_support = graph_artifact.descendant_branch_support_from_index[
            answered_problem_type_index
        ].get(descendant_index, 0.0)
        profile[descendant_index] = -(
            descendant_support_wrong
            * exp(-descendant_decay * float(distance))
            * branch_support
        )
