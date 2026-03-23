from __future__ import annotations

from loguru import logger

from src.math_models.entrance_assessment.types import RuntimeSnapshot, SelectionResult


def should_stop(
    runtime: RuntimeSnapshot,
    selection: SelectionResult,
    entropy_stop: float,
    utility_stop: float,
    leader_probability_stop: float | None,
    max_questions: int,
) -> tuple[bool, str]:
    asked_count = len(runtime.asked_problem_type_indices)
    normalized_entropy = runtime.normalized_entropy

    logger.info(
        "Evaluating entrance assessment stop rule: asked_count={}, max_questions={}, normalized_entropy={:.6f}, entropy_stop={:.6f}, max_utility={:.6f}, utility_stop={:.6f}, leader_state_probability={:.6e}, leader_probability_stop={}",
        asked_count,
        max_questions,
        normalized_entropy,
        entropy_stop,
        selection.max_utility,
        utility_stop,
        runtime.leader_state_probability,
        leader_probability_stop,
    )

    if asked_count >= max_questions:
        return True, "max_questions"

    if selection.problem_type_index is None:
        return True, "no_unanswered_problem_type"

    if (
        normalized_entropy <= entropy_stop
        and selection.max_utility <= utility_stop
    ):
        return True, "normalized_entropy_and_utility"

    if leader_probability_stop is not None:
        if (
            runtime.leader_state_probability >= leader_probability_stop
            and selection.max_utility <= utility_stop
        ):
            return True, "leader_probability_and_utility"

    return False, "continue"
