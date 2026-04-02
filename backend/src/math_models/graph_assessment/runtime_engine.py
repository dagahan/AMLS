from __future__ import annotations

import math
import uuid
from collections.abc import Mapping

import numpy as np
from numpy.typing import NDArray

from src.core.logging import get_logger
from src.models.pydantic.assessment_runtime import (
    ExactInferenceArtifact,
    FinalResult,
    GraphArtifact,
    Outcome,
    ProjectionSnapshot,
    ResponseModel,
    RuntimeSnapshot,
    Selection,
    StepResult,
)

FloatVector = NDArray[np.float64]

DEFAULT_PROJECTED_LEARNED_MASTERY_PROBABILITY = 0.85
DEFAULT_PROJECTED_UNLEARNED_MASTERY_PROBABILITY = 0.15
DEFAULT_PROJECTION_CONFIDENCE_STOP = 0.85
DEFAULT_FRONTIER_CONFIDENCE_STOP = 0.80
OUTER_FRINGE_SELECTION_BONUS = 1.25
READY_SELECTION_BONUS = 1.10

logger = get_logger(__name__)


def initialize_runtime(
    exact_inference_artifact: ExactInferenceArtifact,
    temperature_sharpening: float,
) -> RuntimeSnapshot:
    node_count = len(exact_inference_artifact.parent_by_index)
    node_scores = np.zeros(node_count, dtype=np.float64)
    posterior_summary = _build_posterior_summary(
        exact_inference_artifact=exact_inference_artifact,
        node_scores=node_scores,
        temperature_sharpening=temperature_sharpening,
    )
    runtime_snapshot = RuntimeSnapshot(
        node_scores=node_scores,
        marginal_probabilities=posterior_summary["marginal_probabilities"],
        initial_entropy=exact_inference_artifact.initial_entropy,
        current_entropy=posterior_summary["current_entropy"],
        current_temperature=posterior_summary["current_temperature"],
        asked_node_indices=(),
        leader_state_index=posterior_summary["leader_state_index"],
        leader_state_probability=posterior_summary["leader_state_probability"],
        leader_node_indices=posterior_summary["leader_node_indices"],
    )

    logger.info(
        "Initialized assessment runtime: node_count={}, feasible_state_count={}, initial_entropy={}, leader_state_probability={}",
        node_count,
        exact_inference_artifact.feasible_state_count,
        exact_inference_artifact.initial_entropy,
        runtime_snapshot.leader_state_probability,
    )
    return runtime_snapshot


def restore_runtime(
    graph_artifact: GraphArtifact,
    exact_inference_artifact: ExactInferenceArtifact,
    node_score_by_id: Mapping[uuid.UUID, float],
    asked_node_ids: tuple[uuid.UUID, ...],
    temperature_sharpening: float,
) -> RuntimeSnapshot:
    node_scores = np.zeros(len(graph_artifact.node_ids), dtype=np.float64)
    for node_id, node_score in node_score_by_id.items():
        node_index = graph_artifact.index_by_id.get(node_id)
        if node_index is None:
            continue
        node_scores[node_index] = float(node_score)

    asked_node_indices = tuple(
        dict.fromkeys(
            graph_artifact.index_by_id[node_id]
            for node_id in asked_node_ids
            if node_id in graph_artifact.index_by_id
        )
    )
    runtime_snapshot = _build_runtime_snapshot(
        exact_inference_artifact=exact_inference_artifact,
        node_scores=node_scores,
        asked_node_indices=asked_node_indices,
        temperature_sharpening=temperature_sharpening,
    )
    logger.info(
        "Restored assessment runtime: node_count={}, asked_count={}, normalized_entropy={}, leader_state_probability={}",
        len(graph_artifact.node_ids),
        len(asked_node_indices),
        runtime_snapshot.normalized_entropy,
        runtime_snapshot.leader_state_probability,
    )
    return runtime_snapshot


def apply_answer_step(
    graph_artifact: GraphArtifact,
    exact_inference_artifact: ExactInferenceArtifact,
    runtime: RuntimeSnapshot,
    answered_node_id: uuid.UUID,
    outcome: Outcome,
    instance_difficulty_weight: float,
    response_model: ResponseModel,
    i_dont_know_scalar: float,
    temperature_sharpening: float,
    entropy_stop: float,
    utility_stop: float,
    leader_probability_stop: float | None,
    max_questions: int,
    available_node_ids: set[uuid.UUID],
    learned_mastery_probability: float = DEFAULT_PROJECTED_LEARNED_MASTERY_PROBABILITY,
    unlearned_mastery_probability: float = DEFAULT_PROJECTED_UNLEARNED_MASTERY_PROBABILITY,
    projection_confidence_stop: float = DEFAULT_PROJECTION_CONFIDENCE_STOP,
    frontier_confidence_stop: float = DEFAULT_FRONTIER_CONFIDENCE_STOP,
) -> StepResult:
    answered_node_index = graph_artifact.index_by_id[answered_node_id]
    previous_mastery_probability = float(
        runtime.marginal_probabilities[answered_node_index]
    )
    updated_node_scores = runtime.node_scores.astype(np.float64).copy()
    evidence_weight = float(instance_difficulty_weight)
    if outcome == Outcome.I_DONT_KNOW:
        evidence_weight *= float(i_dont_know_scalar)

    evidence_increment = _build_evidence_increment(
        response_model=response_model,
        outcome=outcome,
        evidence_weight=evidence_weight,
    )
    previous_score = float(updated_node_scores[answered_node_index])
    updated_node_scores[answered_node_index] = previous_score + evidence_increment
    asked_node_indices = tuple(
        dict.fromkeys(
            [*runtime.asked_node_indices, answered_node_index]
        )
    )
    updated_runtime = _build_runtime_snapshot(
        exact_inference_artifact=exact_inference_artifact,
        node_scores=updated_node_scores,
        asked_node_indices=asked_node_indices,
        temperature_sharpening=temperature_sharpening,
    )
    updated_mastery_probability = float(
        updated_runtime.marginal_probabilities[answered_node_index]
    )
    projection_snapshot = _build_projection_snapshot(
        graph_artifact=graph_artifact,
        marginal_probabilities=updated_runtime.marginal_probabilities,
        learned_mastery_probability=learned_mastery_probability,
        unlearned_mastery_probability=unlearned_mastery_probability,
    )
    selection = _select_next_node(
        graph_artifact=graph_artifact,
        runtime=updated_runtime,
        projection_snapshot=projection_snapshot,
        available_node_ids=available_node_ids,
    )
    should_stop_result, stop_reason = should_stop(
        graph_artifact=graph_artifact,
        runtime=updated_runtime,
        selection=selection,
        entropy_stop=entropy_stop,
        utility_stop=utility_stop,
        leader_probability_stop=leader_probability_stop,
        max_questions=max_questions,
        learned_mastery_probability=learned_mastery_probability,
        unlearned_mastery_probability=unlearned_mastery_probability,
        projection_confidence_stop=projection_confidence_stop,
        frontier_confidence_stop=frontier_confidence_stop,
    )

    logger.info(
        "Applied assessment answer: node_id={}, node_index={}, outcome={}, difficulty_weight={}, evidence_increment={}, mastery_probability_before={}, mastery_probability_after={}, previous_score={}, updated_score={}, normalized_entropy={}, projection_confidence={}, frontier_confidence={}, leader_state_probability={}, next_node_id={}, max_utility={}, stop={}, stop_reason={}",
        answered_node_id,
        answered_node_index,
        outcome,
        instance_difficulty_weight,
        evidence_increment,
        previous_mastery_probability,
        updated_mastery_probability,
        previous_score,
        float(updated_node_scores[answered_node_index]),
        _build_normalized_entropy(
            initial_entropy=updated_runtime.initial_entropy,
            current_entropy=updated_runtime.current_entropy,
        ),
        projection_snapshot.projection_confidence,
        projection_snapshot.frontier_confidence,
        updated_runtime.leader_state_probability,
        selection.node_id,
        selection.max_utility,
        should_stop_result,
        stop_reason,
    )

    return StepResult(
        runtime=updated_runtime,
        selection=selection,
        should_stop=should_stop_result,
        stop_reason=stop_reason,
    )


def build_final_result(
    graph_artifact: GraphArtifact,
    runtime: RuntimeSnapshot,
    learned_mastery_probability: float = DEFAULT_PROJECTED_LEARNED_MASTERY_PROBABILITY,
    unlearned_mastery_probability: float = DEFAULT_PROJECTED_UNLEARNED_MASTERY_PROBABILITY,
) -> FinalResult:
    projection_snapshot = _build_projection_snapshot(
        graph_artifact=graph_artifact,
        marginal_probabilities=runtime.marginal_probabilities,
        learned_mastery_probability=learned_mastery_probability,
        unlearned_mastery_probability=unlearned_mastery_probability,
    )
    learned_node_ids = tuple(
        graph_artifact.node_ids[index]
        for index in projection_snapshot.learned_node_indices
    )
    inner_fringe_node_ids = tuple(
        graph_artifact.node_ids[index]
        for index in projection_snapshot.inner_fringe_node_indices
    )
    outer_fringe_node_ids = tuple(
        graph_artifact.node_ids[index]
        for index in projection_snapshot.outer_fringe_node_indices
    )

    logger.info(
        "Built assessment final result: state_index={}, projection_confidence={}, frontier_confidence={}, leader_state_probability={}, learned_count={}, inner_fringe_count={}, outer_fringe_count={}, uncertain_count={}",
        runtime.leader_state_index,
        projection_snapshot.projection_confidence,
        projection_snapshot.frontier_confidence,
        runtime.leader_state_probability,
        len(learned_node_ids),
        len(inner_fringe_node_ids),
        len(outer_fringe_node_ids),
        len(projection_snapshot.uncertain_node_indices),
    )

    return FinalResult(
        state_index=runtime.leader_state_index or 1,
        state_probability=projection_snapshot.projection_confidence,
        learned_node_ids=learned_node_ids,
        inner_fringe_node_ids=inner_fringe_node_ids,
        outer_fringe_node_ids=outer_fringe_node_ids,
    )


def select_next_node(
    graph_artifact: GraphArtifact,
    runtime: RuntimeSnapshot,
    available_node_ids: set[uuid.UUID] | None = None,
    learned_mastery_probability: float = DEFAULT_PROJECTED_LEARNED_MASTERY_PROBABILITY,
    unlearned_mastery_probability: float = DEFAULT_PROJECTED_UNLEARNED_MASTERY_PROBABILITY,
) -> Selection:
    projection_snapshot = _build_projection_snapshot(
        graph_artifact=graph_artifact,
        marginal_probabilities=runtime.marginal_probabilities,
        learned_mastery_probability=learned_mastery_probability,
        unlearned_mastery_probability=unlearned_mastery_probability,
    )
    return _select_next_node(
        graph_artifact=graph_artifact,
        runtime=runtime,
        projection_snapshot=projection_snapshot,
        available_node_ids=available_node_ids or set(graph_artifact.node_ids),
    )


def should_stop(
    graph_artifact: GraphArtifact,
    runtime: RuntimeSnapshot,
    selection: Selection,
    entropy_stop: float,
    utility_stop: float,
    leader_probability_stop: float | None,
    max_questions: int,
    learned_mastery_probability: float = DEFAULT_PROJECTED_LEARNED_MASTERY_PROBABILITY,
    unlearned_mastery_probability: float = DEFAULT_PROJECTED_UNLEARNED_MASTERY_PROBABILITY,
    projection_confidence_stop: float = DEFAULT_PROJECTION_CONFIDENCE_STOP,
    frontier_confidence_stop: float = DEFAULT_FRONTIER_CONFIDENCE_STOP,
) -> tuple[bool, str | None]:
    asked_count = len(runtime.asked_node_indices)

    if asked_count >= max_questions:
        logger.info(
            "Assessment stop by question cap: asked_count={}, max_questions={}",
            asked_count,
            max_questions,
        )
        return True, "max_questions"

    if selection.node_id is None:
        logger.info("Assessment stop because no next node is available")
        return True, "no_available_node"

    projection_snapshot = _build_projection_snapshot(
        graph_artifact=graph_artifact,
        marginal_probabilities=runtime.marginal_probabilities,
        learned_mastery_probability=learned_mastery_probability,
        unlearned_mastery_probability=unlearned_mastery_probability,
    )
    normalized_entropy = _build_normalized_entropy(
        initial_entropy=runtime.initial_entropy,
        current_entropy=runtime.current_entropy,
    )
    entropy_ready = normalized_entropy <= float(entropy_stop)
    utility_ready = selection.max_utility <= float(utility_stop)
    projection_ready = (
        projection_snapshot.projection_confidence
        >= float(projection_confidence_stop)
    )
    frontier_ready = (
        projection_snapshot.frontier_confidence
        >= float(frontier_confidence_stop)
    )

    if leader_probability_stop is not None:
        logger.debug(
            "Ignoring leader_probability_stop for stopping because projection confidence drives the product stop: leader_probability_stop={}, leader_state_probability={}",
            leader_probability_stop,
            runtime.leader_state_probability,
        )

    if entropy_ready and utility_ready and projection_ready and frontier_ready:
        logger.info(
            "Assessment stop by projection convergence: normalized_entropy={}, entropy_stop={}, max_utility={}, utility_stop={}, projection_confidence={}, projection_confidence_stop={}, frontier_confidence={}, frontier_confidence_stop={}, leader_state_probability={}",
            normalized_entropy,
            entropy_stop,
            selection.max_utility,
            utility_stop,
            projection_snapshot.projection_confidence,
            projection_confidence_stop,
            projection_snapshot.frontier_confidence,
            frontier_confidence_stop,
            runtime.leader_state_probability,
        )
        return True, "converged_projection"

    logger.debug(
        "Assessment continues: normalized_entropy={}, entropy_stop={}, max_utility={}, utility_stop={}, projection_confidence={}, projection_confidence_stop={}, frontier_confidence={}, frontier_confidence_stop={}, leader_state_probability={}, uncertain_count={}",
        normalized_entropy,
        entropy_stop,
        selection.max_utility,
        utility_stop,
        projection_snapshot.projection_confidence,
        projection_confidence_stop,
        projection_snapshot.frontier_confidence,
        frontier_confidence_stop,
        runtime.leader_state_probability,
        len(projection_snapshot.uncertain_node_indices),
    )
    return False, None


def _build_runtime_snapshot(
    exact_inference_artifact: ExactInferenceArtifact,
    node_scores: FloatVector,
    asked_node_indices: tuple[int, ...],
    temperature_sharpening: float,
) -> RuntimeSnapshot:
    posterior_summary = _build_posterior_summary(
        exact_inference_artifact=exact_inference_artifact,
        node_scores=node_scores,
        temperature_sharpening=temperature_sharpening,
    )
    runtime_snapshot = RuntimeSnapshot(
        node_scores=node_scores,
        marginal_probabilities=posterior_summary["marginal_probabilities"],
        initial_entropy=exact_inference_artifact.initial_entropy,
        current_entropy=posterior_summary["current_entropy"],
        current_temperature=posterior_summary["current_temperature"],
        asked_node_indices=asked_node_indices,
        leader_state_index=posterior_summary["leader_state_index"],
        leader_state_probability=posterior_summary["leader_state_probability"],
        leader_node_indices=posterior_summary["leader_node_indices"],
    )

    logger.debug(
        "Built assessment runtime snapshot: asked_count={}, entropy={}, normalized_entropy={}, leader_state_probability={}, leader_node_count={}",
        len(asked_node_indices),
        runtime_snapshot.current_entropy,
        _build_normalized_entropy(
            initial_entropy=runtime_snapshot.initial_entropy,
            current_entropy=runtime_snapshot.current_entropy,
        ),
        runtime_snapshot.leader_state_probability,
        len(runtime_snapshot.leader_node_indices),
    )
    return runtime_snapshot


def _build_posterior_summary(
    exact_inference_artifact: ExactInferenceArtifact,
    node_scores: FloatVector,
    temperature_sharpening: float,
) -> dict[str, object]:
    log_zero_by_index, log_one_by_index = _build_subtree_log_partition_arrays(
        exact_inference_artifact=exact_inference_artifact,
        node_scores=node_scores,
    )
    marginal_probabilities = _build_marginal_probabilities(
        exact_inference_artifact=exact_inference_artifact,
        log_zero_by_index=log_zero_by_index,
        log_one_by_index=log_one_by_index,
    )
    log_partition = sum(
        np.logaddexp(log_zero_by_index[root_index], log_one_by_index[root_index])
        for root_index in exact_inference_artifact.root_indices
    )
    expected_log_weight = float(np.dot(marginal_probabilities, node_scores))
    current_entropy = float(log_partition - expected_log_weight)
    normalized_entropy = _build_normalized_entropy(
        initial_entropy=exact_inference_artifact.initial_entropy,
        current_entropy=current_entropy,
    )
    current_temperature = 1.0 + (
        float(temperature_sharpening) * max(0.0, 1.0 - normalized_entropy)
    )
    leader_node_indices, leader_log_weight = _build_leader_state(
        exact_inference_artifact=exact_inference_artifact,
        node_scores=node_scores,
    )
    raw_state_index = _build_state_rank(
        exact_inference_artifact=exact_inference_artifact,
        leader_node_indices=leader_node_indices,
    )
    stable_state_index = raw_state_index % 2_147_483_647 or 1
    leader_state_probability = float(math.exp(leader_log_weight - log_partition))

    logger.debug(
        "Built assessment posterior summary: log_partition={}, expected_log_weight={}, entropy={}, normalized_entropy={}, stable_state_index={}, raw_state_index={}, leader_state_probability={}",
        float(log_partition),
        expected_log_weight,
        current_entropy,
        normalized_entropy,
        stable_state_index,
        raw_state_index,
        leader_state_probability,
    )

    return {
        "marginal_probabilities": marginal_probabilities,
        "current_entropy": current_entropy,
        "current_temperature": current_temperature,
        "leader_state_index": stable_state_index,
        "leader_state_probability": leader_state_probability,
        "leader_node_indices": leader_node_indices,
        "log_partition": float(log_partition),
    }


def _build_subtree_log_partition_arrays(
    exact_inference_artifact: ExactInferenceArtifact,
    node_scores: FloatVector,
) -> tuple[FloatVector, FloatVector]:
    node_count = len(exact_inference_artifact.parent_by_index)
    log_zero_by_index = np.zeros(node_count, dtype=np.float64)
    log_one_by_index = np.zeros(node_count, dtype=np.float64)

    for node_index in exact_inference_artifact.postorder_indices:
        zero_score = 0.0
        one_score = float(node_scores[node_index])

        for child_index in exact_inference_artifact.children_by_index[node_index]:
            zero_score += float(log_zero_by_index[child_index])
            one_score += float(
                np.logaddexp(
                    log_zero_by_index[child_index],
                    log_one_by_index[child_index],
                )
            )

        log_zero_by_index[node_index] = zero_score
        log_one_by_index[node_index] = one_score

        logger.debug(
            "Computed subtree partition scores: node_index={}, zero_score={}, one_score={}",
            node_index,
            zero_score,
            one_score,
        )

    return log_zero_by_index, log_one_by_index


def _build_marginal_probabilities(
    exact_inference_artifact: ExactInferenceArtifact,
    log_zero_by_index: FloatVector,
    log_one_by_index: FloatVector,
) -> FloatVector:
    node_count = len(exact_inference_artifact.parent_by_index)
    marginal_probabilities = np.zeros(node_count, dtype=np.float64)

    for node_index in exact_inference_artifact.preorder_indices:
        parent_index = exact_inference_artifact.parent_by_index[node_index]
        node_log_total = float(
            np.logaddexp(log_zero_by_index[node_index], log_one_by_index[node_index])
        )
        conditional_mastery_probability = math.exp(
            float(log_one_by_index[node_index]) - node_log_total
        )

        if parent_index is None:
            marginal_probabilities[node_index] = conditional_mastery_probability
        else:
            marginal_probabilities[node_index] = (
                marginal_probabilities[parent_index]
                * conditional_mastery_probability
            )

        logger.debug(
            "Computed mastery marginal: node_index={}, parent_index={}, probability={}",
            node_index,
            parent_index,
            float(marginal_probabilities[node_index]),
        )

    return marginal_probabilities


def _build_leader_state(
    exact_inference_artifact: ExactInferenceArtifact,
    node_scores: FloatVector,
) -> tuple[tuple[int, ...], float]:
    node_count = len(exact_inference_artifact.parent_by_index)
    best_zero_by_index = np.zeros(node_count, dtype=np.float64)
    best_one_by_index = np.zeros(node_count, dtype=np.float64)

    for node_index in exact_inference_artifact.postorder_indices:
        best_zero_score = 0.0
        best_one_score = float(node_scores[node_index])

        for child_index in exact_inference_artifact.children_by_index[node_index]:
            best_zero_score += float(best_zero_by_index[child_index])
            best_one_score += max(
                float(best_zero_by_index[child_index]),
                float(best_one_by_index[child_index]),
            )

        best_zero_by_index[node_index] = best_zero_score
        best_one_by_index[node_index] = best_one_score

        logger.debug(
            "Computed leader subtree scores: node_index={}, best_zero_score={}, best_one_score={}",
            node_index,
            best_zero_score,
            best_one_score,
        )

    is_mastered_by_index = np.zeros(node_count, dtype=np.bool_)

    def restore_state(node_index: int, parent_is_mastered: bool) -> None:
        if not parent_is_mastered:
            is_mastered_by_index[node_index] = False
            for child_index in exact_inference_artifact.children_by_index[node_index]:
                restore_state(child_index, False)
            return

        child_is_mastered = (
            float(best_one_by_index[node_index])
            > float(best_zero_by_index[node_index])
        )
        is_mastered_by_index[node_index] = child_is_mastered

        for child_index in exact_inference_artifact.children_by_index[node_index]:
            restore_state(child_index, child_is_mastered)

    leader_log_weight = 0.0

    for root_index in exact_inference_artifact.root_indices:
        root_is_mastered = (
            float(best_one_by_index[root_index])
            > float(best_zero_by_index[root_index])
        )
        leader_log_weight += max(
            float(best_zero_by_index[root_index]),
            float(best_one_by_index[root_index]),
        )
        is_mastered_by_index[root_index] = root_is_mastered

        for child_index in exact_inference_artifact.children_by_index[root_index]:
            restore_state(child_index, root_is_mastered)

    leader_node_indices = tuple(
        index
        for index in exact_inference_artifact.preorder_indices
        if bool(is_mastered_by_index[index])
    )

    logger.debug(
        "Built leader state: leader_node_count={}, leader_log_weight={}",
        len(leader_node_indices),
        leader_log_weight,
    )
    return leader_node_indices, float(leader_log_weight)


def _build_state_rank(
    exact_inference_artifact: ExactInferenceArtifact,
    leader_node_indices: tuple[int, ...],
) -> int:
    subtree_state_count_by_index = _build_subtree_state_counts(exact_inference_artifact)
    learned_index_set = set(leader_node_indices)

    def build_subtree_rank(node_index: int) -> int:
        if node_index not in learned_index_set:
            return 0

        state_rank = 1
        multiplier = 1

        for child_index in reversed(exact_inference_artifact.children_by_index[node_index]):
            child_rank = build_subtree_rank(child_index)
            state_rank += child_rank * multiplier
            multiplier *= subtree_state_count_by_index[child_index]

        return state_rank

    state_rank = 0
    multiplier = 1

    for root_index in reversed(exact_inference_artifact.root_indices):
        root_rank = build_subtree_rank(root_index)
        state_rank += root_rank * multiplier
        multiplier *= subtree_state_count_by_index[root_index]

    logger.debug("Built leader state rank: raw_state_rank={}", state_rank)
    return state_rank


def _build_subtree_state_counts(
    exact_inference_artifact: ExactInferenceArtifact,
) -> dict[int, int]:
    subtree_state_count_by_index: dict[int, int] = {}

    for node_index in exact_inference_artifact.postorder_indices:
        child_state_product = 1

        for child_index in exact_inference_artifact.children_by_index[node_index]:
            child_state_product *= subtree_state_count_by_index[child_index]

        subtree_state_count_by_index[node_index] = 1 + child_state_product

    return subtree_state_count_by_index


def _select_next_node(
    graph_artifact: GraphArtifact,
    runtime: RuntimeSnapshot,
    projection_snapshot: ProjectionSnapshot,
    available_node_ids: set[uuid.UUID],
) -> Selection:
    asked_node_indices = set(runtime.asked_node_indices)
    learned_node_indices = set(projection_snapshot.learned_node_indices)
    outer_fringe_node_indices = set(
        projection_snapshot.outer_fringe_node_indices
    )
    available_node_indices = {
        graph_artifact.index_by_id[node_id]
        for node_id in available_node_ids
        if node_id in graph_artifact.index_by_id
    }

    selected_node_index: int | None = None
    selected_node_id: uuid.UUID | None = None
    selected_mastery_probability = 0.0
    selected_utility = 0.0
    selected_score = -1.0

    candidate_groups = (
        tuple(
            node_index
            for node_index in graph_artifact.topological_order
            if node_index in outer_fringe_node_indices
        ),
        tuple(graph_artifact.topological_order),
    )

    for candidate_group in candidate_groups:
        for node_index in candidate_group:
            if node_index not in available_node_indices:
                continue

            if node_index in asked_node_indices:
                continue

            mastery_probability = float(runtime.marginal_probabilities[node_index])
            utility = 4.0 * mastery_probability * (1.0 - mastery_probability)
            selection_score = utility

            if node_index in outer_fringe_node_indices:
                selection_score *= OUTER_FRINGE_SELECTION_BONUS
            elif all(
                prerequisite_index in learned_node_indices
                for prerequisite_index in graph_artifact.prerequisites_by_index[node_index]
            ):
                selection_score *= READY_SELECTION_BONUS

            if selection_score > selected_score:
                selected_node_index = node_index
                selected_node_id = graph_artifact.node_ids[node_index]
                selected_mastery_probability = mastery_probability
                selected_utility = utility
                selected_score = selection_score

        if selected_node_id is not None:
            break

    logger.debug(
        "Selected next assessment node: node_id={}, node_index={}, mastery_probability={}, utility={}, selection_score={}, projected_outer_fringe_count={}",
        selected_node_id,
        selected_node_index,
        selected_mastery_probability,
        selected_utility,
        selected_score,
        len(projection_snapshot.outer_fringe_node_indices),
    )

    return Selection(
        node_id=selected_node_id,
        node_index=selected_node_index,
        mastery_probability=selected_mastery_probability,
        max_utility=selected_utility,
    )


def _build_evidence_increment(
    response_model: ResponseModel,
    outcome: Outcome,
    evidence_weight: float,
) -> float:
    mastered_probability = _build_outcome_probability(
        response_model=response_model,
        outcome=outcome,
        is_mastered=True,
    )
    unmastered_probability = _build_outcome_probability(
        response_model=response_model,
        outcome=outcome,
        is_mastered=False,
    )
    likelihood_ratio = mastered_probability / unmastered_probability
    evidence_increment = float(evidence_weight) * math.log(likelihood_ratio)

    logger.debug(
        "Built evidence increment: outcome={}, evidence_weight={}, mastered_probability={}, unmastered_probability={}, evidence_increment={}",
        outcome,
        evidence_weight,
        mastered_probability,
        unmastered_probability,
        evidence_increment,
    )
    return evidence_increment


def _build_outcome_probability(
    response_model: ResponseModel,
    outcome: Outcome,
    is_mastered: bool,
) -> float:
    if is_mastered:
        if outcome == Outcome.CORRECT:
            return response_model.mastered_right
        if outcome == Outcome.INCORRECT:
            return response_model.mastered_wrong
        return response_model.mastered_i_dont_know

    if outcome == Outcome.CORRECT:
        return response_model.unmastered_right
    if outcome == Outcome.INCORRECT:
        return response_model.unmastered_wrong
    return response_model.unmastered_i_dont_know


def _build_projection_snapshot(
    graph_artifact: GraphArtifact,
    marginal_probabilities: FloatVector,
    learned_mastery_probability: float,
    unlearned_mastery_probability: float,
) -> ProjectionSnapshot:
    learned_node_indices_set: set[int] = set()
    uncertain_node_indices: list[int] = []

    for node_index in graph_artifact.topological_order:
        mastery_probability = float(marginal_probabilities[node_index])
        prerequisites_are_learned = all(
            prerequisite_index in learned_node_indices_set
            for prerequisite_index in graph_artifact.prerequisites_by_index[node_index]
        )

        if mastery_probability >= learned_mastery_probability and prerequisites_are_learned:
            learned_node_indices_set.add(node_index)
            continue

        if (
            mastery_probability > unlearned_mastery_probability
            and mastery_probability < learned_mastery_probability
        ):
            uncertain_node_indices.append(node_index)

    learned_node_indices = tuple(
        node_index
        for node_index in graph_artifact.topological_order
        if node_index in learned_node_indices_set
    )
    inner_fringe_node_indices = tuple(
        node_index
        for node_index in learned_node_indices
        if any(
            child_index not in learned_node_indices_set
            for child_index in graph_artifact.dependents_by_index[node_index]
        )
    )
    outer_fringe_node_indices = tuple(
        node_index
        for node_index in graph_artifact.topological_order
        if node_index not in learned_node_indices_set
        and all(
            prerequisite_index in learned_node_indices_set
            for prerequisite_index in graph_artifact.prerequisites_by_index[node_index]
        )
    )

    projection_confidence_values: list[float] = []
    for node_index in graph_artifact.topological_order:
        mastery_probability = float(marginal_probabilities[node_index])
        if node_index in learned_node_indices_set:
            projection_confidence_values.append(mastery_probability)
        else:
            projection_confidence_values.append(1.0 - mastery_probability)

    projection_confidence = (
        float(sum(projection_confidence_values) / len(projection_confidence_values))
        if projection_confidence_values
        else 1.0
    )

    frontier_confidence_values = [
        float(marginal_probabilities[node_index])
        for node_index in inner_fringe_node_indices
    ]
    frontier_confidence_values.extend(
        1.0 - float(marginal_probabilities[node_index])
        for node_index in outer_fringe_node_indices
    )
    frontier_confidence = (
        float(sum(frontier_confidence_values) / len(frontier_confidence_values))
        if frontier_confidence_values
        else projection_confidence
    )

    projection_snapshot = ProjectionSnapshot(
        learned_node_indices=learned_node_indices,
        inner_fringe_node_indices=inner_fringe_node_indices,
        outer_fringe_node_indices=outer_fringe_node_indices,
        uncertain_node_indices=tuple(uncertain_node_indices),
        projection_confidence=projection_confidence,
        frontier_confidence=frontier_confidence,
    )

    logger.debug(
        "Built projection snapshot: learned_count={}, inner_fringe_count={}, outer_fringe_count={}, uncertain_count={}, projection_confidence={}, frontier_confidence={}, learned_mastery_probability={}, unlearned_mastery_probability={}",
        len(projection_snapshot.learned_node_indices),
        len(projection_snapshot.inner_fringe_node_indices),
        len(projection_snapshot.outer_fringe_node_indices),
        len(projection_snapshot.uncertain_node_indices),
        projection_snapshot.projection_confidence,
        projection_snapshot.frontier_confidence,
        learned_mastery_probability,
        unlearned_mastery_probability,
    )
    return projection_snapshot


def _build_normalized_entropy(
    initial_entropy: float,
    current_entropy: float,
) -> float:
    if initial_entropy <= 0.0:
        return 0.0

    return current_entropy / initial_entropy
