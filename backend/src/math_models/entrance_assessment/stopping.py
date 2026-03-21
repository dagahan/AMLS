from __future__ import annotations

from src.math_models.entrance_assessment.types import RuntimeSnapshot, SelectionResult


def should_stop(
    runtime: RuntimeSnapshot,
    selection: SelectionResult,
    entropy_stop: float,
    utility_stop: float,
    leader_probability_stop: float,
    max_questions: int,
) -> tuple[bool, str | None]:
    asked_count = len(runtime.asked_problem_type_indices)
    if asked_count >= max_questions:
        return True, "max_questions"

    entropy_low_enough = runtime.current_entropy <= entropy_stop
    utility_low_enough = selection.max_utility <= utility_stop
    leader_high_enough = runtime.leader_state_probability >= leader_probability_stop

    if entropy_low_enough and utility_low_enough and leader_high_enough:
        return True, "low_entropy_low_utility"

    if selection.problem_type_index is None:
        return True, "no_available_problem_type"

    return False, None
