from __future__ import annotations

import uuid

import numpy as np

from src.math_models.entrance_assessment import (
    Outcome,
    apply_answer_step,
    build_final_result,
    build_graph_artifact,
    build_state_artifact,
    initialize_runtime,
    select_next_problem_type,
    should_stop,
)
from src.math_models.entrance_assessment.probability import calculate_state_probabilities
from src.math_models.entrance_assessment.support_profile import build_support_profile


I_DONT_KNOW_SCALAR = 1.4
ANCESTOR_SUPPORT_CORRECT = 0.85
ANCESTOR_SUPPORT_WRONG = 0.12
DESCENDANT_SUPPORT_CORRECT = 0.25
DESCENDANT_SUPPORT_WRONG = 0.90
ANCESTOR_DECAY = 0.70
DESCENDANT_DECAY = 0.90
BRANCH_PENALTY_EXPONENT = 1.0
TEMPERATURE_SHARPENING = 1.5
ENTROPY_STOP = 0.90
UTILITY_STOP = 0.18
LEADER_PROBABILITY_STOP = 0.80
MAX_QUESTIONS = 16
EPSILON = 1e-9


def test_state_artifact_contains_only_feasible_states() -> None:
    root_id = uuid.uuid4()
    left_id = uuid.uuid4()
    right_id = uuid.uuid4()
    graph_artifact = build_graph_artifact(
        problem_type_ids=(root_id, left_id, right_id),
        prerequisite_edges=((left_id, root_id), (right_id, root_id)),
        branch_penalty_exponent=1.0,
    )

    state_artifact = build_state_artifact(graph_artifact)

    assert len(state_artifact.state_masks) == 5
    assert 0 in state_artifact.state_index_by_mask
    assert (1 << 1) not in state_artifact.state_index_by_mask
    assert (1 << 2) not in state_artifact.state_index_by_mask


def test_i_dont_know_profile_is_scaled_incorrect_profile() -> None:
    root_id = uuid.uuid4()
    child_id = uuid.uuid4()
    graph_artifact = build_graph_artifact(
        problem_type_ids=(root_id, child_id),
        prerequisite_edges=((child_id, root_id),),
        branch_penalty_exponent=1.0,
    )

    incorrect_profile = build_support_profile(
        graph_artifact=graph_artifact,
        answered_problem_type_index=1,
        outcome=Outcome.INCORRECT,
        i_dont_know_scalar=I_DONT_KNOW_SCALAR,
        ancestor_support_correct=ANCESTOR_SUPPORT_CORRECT,
        ancestor_support_wrong=ANCESTOR_SUPPORT_WRONG,
        descendant_support_correct=DESCENDANT_SUPPORT_CORRECT,
        descendant_support_wrong=DESCENDANT_SUPPORT_WRONG,
        ancestor_decay=ANCESTOR_DECAY,
        descendant_decay=DESCENDANT_DECAY,
    )
    i_dont_know_profile = build_support_profile(
        graph_artifact=graph_artifact,
        answered_problem_type_index=1,
        outcome=Outcome.I_DONT_KNOW,
        i_dont_know_scalar=I_DONT_KNOW_SCALAR,
        ancestor_support_correct=ANCESTOR_SUPPORT_CORRECT,
        ancestor_support_wrong=ANCESTOR_SUPPORT_WRONG,
        descendant_support_correct=DESCENDANT_SUPPORT_CORRECT,
        descendant_support_wrong=DESCENDANT_SUPPORT_WRONG,
        ancestor_decay=ANCESTOR_DECAY,
        descendant_decay=DESCENDANT_DECAY,
    )

    assert np.allclose(i_dont_know_profile, incorrect_profile * 1.4)


def test_graph_artifact_rejects_cycles() -> None:
    root_id = uuid.uuid4()
    child_id = uuid.uuid4()

    try:
        build_graph_artifact(
            problem_type_ids=(root_id, child_id),
            prerequisite_edges=((child_id, root_id), (root_id, child_id)),
            branch_penalty_exponent=1.0,
        )
    except ValueError as error:
        assert str(error) == "Problem type graph must be acyclic"
        return

    raise AssertionError("Cyclic graph should raise ValueError")


def test_initial_selection_prefers_most_informative_problem_type() -> None:
    root_id = uuid.uuid4()
    child_id = uuid.uuid4()
    graph_artifact = build_graph_artifact(
        problem_type_ids=(root_id, child_id),
        prerequisite_edges=((child_id, root_id),),
        branch_penalty_exponent=1.0,
    )
    state_artifact = build_state_artifact(graph_artifact)
    runtime = initialize_runtime(state_artifact)

    selection = select_next_problem_type(
        graph_artifact=graph_artifact,
        state_artifact=state_artifact,
        runtime=runtime,
        available_problem_type_indices={0, 1},
    )

    assert selection.problem_type_id == root_id
    assert selection.max_utility > 0.0


def test_probability_calculation_normalizes_scores() -> None:
    probabilities, entropy, leader_state_index, leader_state_probability = (
        calculate_state_probabilities(
            state_scores=np.asarray([0.0, 1.0], dtype=np.float64),
            temperature=1.0,
        )
    )

    assert np.isclose(probabilities.sum(), 1.0)
    assert leader_state_index == 1
    assert leader_state_probability > 0.5
    assert entropy > 0.0


def test_engine_builds_final_result_from_correct_chain() -> None:
    root_id = uuid.uuid4()
    child_id = uuid.uuid4()
    graph_artifact = build_graph_artifact(
        problem_type_ids=(root_id, child_id),
        prerequisite_edges=((child_id, root_id),),
        branch_penalty_exponent=1.0,
    )
    state_artifact = build_state_artifact(graph_artifact)
    runtime = initialize_runtime(state_artifact)

    first_step = apply_answer_step(
        graph_artifact=graph_artifact,
        state_artifact=state_artifact,
        runtime=runtime,
        answered_problem_type_id=root_id,
        outcome=Outcome.CORRECT,
        instance_difficulty_weight=1.0,
        i_dont_know_scalar=I_DONT_KNOW_SCALAR,
        ancestor_support_correct=ANCESTOR_SUPPORT_CORRECT,
        ancestor_support_wrong=ANCESTOR_SUPPORT_WRONG,
        descendant_support_correct=DESCENDANT_SUPPORT_CORRECT,
        descendant_support_wrong=DESCENDANT_SUPPORT_WRONG,
        ancestor_decay=ANCESTOR_DECAY,
        descendant_decay=DESCENDANT_DECAY,
        temperature_sharpening=TEMPERATURE_SHARPENING,
        entropy_stop=ENTROPY_STOP,
        utility_stop=UTILITY_STOP,
        leader_probability_stop=LEADER_PROBABILITY_STOP,
        max_questions=MAX_QUESTIONS,
        epsilon=EPSILON,
        available_problem_type_ids={child_id},
    )
    second_step = apply_answer_step(
        graph_artifact=graph_artifact,
        state_artifact=state_artifact,
        runtime=first_step.runtime,
        answered_problem_type_id=child_id,
        outcome=Outcome.CORRECT,
        instance_difficulty_weight=1.0,
        i_dont_know_scalar=I_DONT_KNOW_SCALAR,
        ancestor_support_correct=ANCESTOR_SUPPORT_CORRECT,
        ancestor_support_wrong=ANCESTOR_SUPPORT_WRONG,
        descendant_support_correct=DESCENDANT_SUPPORT_CORRECT,
        descendant_support_wrong=DESCENDANT_SUPPORT_WRONG,
        ancestor_decay=ANCESTOR_DECAY,
        descendant_decay=DESCENDANT_DECAY,
        temperature_sharpening=TEMPERATURE_SHARPENING,
        entropy_stop=ENTROPY_STOP,
        utility_stop=UTILITY_STOP,
        leader_probability_stop=LEADER_PROBABILITY_STOP,
        max_questions=MAX_QUESTIONS,
        epsilon=EPSILON,
        available_problem_type_ids=set(),
    )

    final_result = build_final_result(
        graph_artifact=graph_artifact,
        state_artifact=state_artifact,
        runtime=second_step.runtime,
    )

    assert set(final_result.learned_problem_type_ids) == {root_id, child_id}
    assert final_result.outer_fringe_ids == ()


def test_stop_logic_stops_when_no_problem_type_is_available() -> None:
    root_id = uuid.uuid4()
    graph_artifact = build_graph_artifact(
        problem_type_ids=(root_id,),
        prerequisite_edges=(),
        branch_penalty_exponent=1.0,
    )
    state_artifact = build_state_artifact(graph_artifact)
    runtime = initialize_runtime(state_artifact)
    selection = select_next_problem_type(
        graph_artifact=graph_artifact,
        state_artifact=state_artifact,
        runtime=runtime,
        available_problem_type_indices=set(),
    )

    stop, stop_reason = should_stop(
        runtime=runtime,
        selection=selection,
        entropy_stop=ENTROPY_STOP,
        utility_stop=UTILITY_STOP,
        leader_probability_stop=LEADER_PROBABILITY_STOP,
        max_questions=MAX_QUESTIONS,
    )

    assert stop is True
    assert stop_reason == "no_available_problem_type"
