from __future__ import annotations

from src.math_models.entrance_assessment.types import RuntimeSnapshot, SelectionResult


def should_stop(
    runtime: RuntimeSnapshot,
    selection: SelectionResult,
    entropy_stop: float,
    utility_stop: float,
    leader_probability_stop: float | None,
    max_questions: int,
) -> tuple[bool, str | None]:
    asked_count = len(runtime.asked_problem_type_indices)
    if asked_count >= max_questions:
        return True, "max_questions"

    if selection.problem_type_index is None:
        return True, "no_available_problem_type"

    entropy_low_enough = runtime.current_entropy <= entropy_stop
    utility_low_enough = selection.max_utility <= utility_stop

    if not entropy_low_enough or not utility_low_enough:
        return False, None

    if leader_probability_stop is None:
        return True, "low_entropy_low_utility"

    if runtime.leader_state_probability >= leader_probability_stop:
        return True, "low_entropy_low_utility"

    return False, None
