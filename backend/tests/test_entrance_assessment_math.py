from __future__ import annotations

from typing import TypedDict

import numpy as np
import pytest

from src.core.utils import EnvTools
from src.db.database import DataBase
from src.db.reference_dataset import PROBLEM_TYPE_DATA
from src.math_models.entrance_assessment import (
    Outcome,
    apply_answer_step,
    build_final_result,
    initialize_runtime,
    select_next_problem_type,
)
from src.services.entrance_test import EntranceTestStructureService


EXPECTED_ROOT_COUNT = 8
EXPECTED_EDGE_COUNT = len(PROBLEM_TYPE_DATA) - EXPECTED_ROOT_COUNT
EXPECTED_FEASIBLE_STATE_COUNT = 8_492_446_687_900_032


class AssessmentParameters(TypedDict):
    i_dont_know_scalar: float
    ancestor_support_correct: float
    ancestor_support_wrong: float
    descendant_support_correct: float
    descendant_support_wrong: float
    ancestor_decay: float
    descendant_decay: float
    temperature_sharpening: float
    entropy_stop: float
    utility_stop: float
    leader_probability_stop: float | None
    max_questions: int
    epsilon: float


@pytest.fixture(scope="module")
def assessment_parameters() -> AssessmentParameters:
    return AssessmentParameters(
        i_dont_know_scalar=float(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_I_DONT_KNOW_SCALAR")
        ),
        ancestor_support_correct=float(
            EnvTools.required_load_env_var(
                "ENTRANCE_ASSESSMENT_ANCESTOR_SUPPORT_CORRECT"
            )
        ),
        ancestor_support_wrong=float(
            EnvTools.required_load_env_var(
                "ENTRANCE_ASSESSMENT_ANCESTOR_SUPPORT_WRONG"
            )
        ),
        descendant_support_correct=float(
            EnvTools.required_load_env_var(
                "ENTRANCE_ASSESSMENT_DESCENDANT_SUPPORT_CORRECT"
            )
        ),
        descendant_support_wrong=float(
            EnvTools.required_load_env_var(
                "ENTRANCE_ASSESSMENT_DESCENDANT_SUPPORT_WRONG"
            )
        ),
        ancestor_decay=float(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_ANCESTOR_DECAY")
        ),
        descendant_decay=float(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_DESCENDANT_DECAY")
        ),
        temperature_sharpening=float(
            EnvTools.required_load_env_var(
                "ENTRANCE_ASSESSMENT_TEMPERATURE_SHARPENING"
            )
        ),
        entropy_stop=float(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_ENTROPY_STOP")
        ),
        utility_stop=float(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_UTILITY_STOP")
        ),
        leader_probability_stop=_load_optional_float(
            "ENTRANCE_ASSESSMENT_LEADER_PROBABILITY_STOP"
        ),
        max_questions=int(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_MAX_QUESTIONS")
        ),
        epsilon=float(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_EPSILON")
        ),
    )


@pytest.mark.asyncio
async def test_big_reference_graph_compiles_to_exact_forest_runtime(
    database: DataBase,
) -> None:
    if database.async_session is None:
        raise RuntimeError("Database session factory is not initialized")

    structure_service = EntranceTestStructureService()

    async with database.async_session() as session:
        compile_response = await structure_service.compile_current_structure(session)
        structure_state = await structure_service.load_latest_compiled_structure(session)

    assert compile_response.status == "ready"
    assert compile_response.artifact_kind == "exact_forest_v1"
    assert compile_response.problem_type_count == len(PROBLEM_TYPE_DATA)
    assert compile_response.edge_count == EXPECTED_EDGE_COUNT
    assert compile_response.feasible_state_count == EXPECTED_FEASIBLE_STATE_COUNT
    assert structure_state.forest_artifact.feasible_state_count == EXPECTED_FEASIBLE_STATE_COUNT
    assert len(structure_state.forest_artifact.root_indices) == EXPECTED_ROOT_COUNT
    assert len(structure_state.graph_artifact.node_ids) == len(PROBLEM_TYPE_DATA)
    assert max(structure_state.graph_artifact.indegree_by_index.tolist()) == 1
    assert structure_state.forest_artifact.max_depth >= 1


@pytest.mark.asyncio
async def test_big_reference_graph_runtime_invariants_hold_for_fixed_answer_sequence(
    database: DataBase,
    assessment_parameters: AssessmentParameters,
) -> None:
    if database.async_session is None:
        raise RuntimeError("Database session factory is not initialized")

    structure_service = EntranceTestStructureService()

    async with database.async_session() as session:
        await structure_service.compile_current_structure(session)
        structure_state = await structure_service.load_latest_compiled_structure(session)

    runtime_snapshot = initialize_runtime(
        structure_state.forest_artifact,
        assessment_parameters["temperature_sharpening"],
    )
    answer_outcomes = (
        Outcome.CORRECT,
        Outcome.INCORRECT,
        Outcome.I_DONT_KNOW,
        Outcome.CORRECT,
        Outcome.INCORRECT,
        Outcome.CORRECT,
    )
    selected_problem_type_ids: list[object] = []
    entropies: list[float] = [runtime_snapshot.current_entropy]
    temperatures: list[float] = [runtime_snapshot.current_temperature]

    for answer_outcome in answer_outcomes:
        selection = select_next_problem_type(
            graph_artifact=structure_state.graph_artifact,
            runtime=runtime_snapshot,
        )
        assert selection.problem_type_id is not None
        assert selection.problem_type_id not in selected_problem_type_ids
        selected_problem_type_ids.append(selection.problem_type_id)

        step_result = apply_answer_step(
            graph_artifact=structure_state.graph_artifact,
            forest_artifact=structure_state.forest_artifact,
            runtime=runtime_snapshot,
            answered_problem_type_id=selection.problem_type_id,
            outcome=answer_outcome,
            instance_difficulty_weight=1.0,
            i_dont_know_scalar=assessment_parameters["i_dont_know_scalar"],
            ancestor_support_correct=assessment_parameters["ancestor_support_correct"],
            ancestor_support_wrong=assessment_parameters["ancestor_support_wrong"],
            descendant_support_correct=assessment_parameters["descendant_support_correct"],
            descendant_support_wrong=assessment_parameters["descendant_support_wrong"],
            ancestor_decay=assessment_parameters["ancestor_decay"],
            descendant_decay=assessment_parameters["descendant_decay"],
            temperature_sharpening=assessment_parameters["temperature_sharpening"],
            entropy_stop=assessment_parameters["entropy_stop"],
            utility_stop=assessment_parameters["utility_stop"],
            leader_probability_stop=_coerce_optional_float(
                assessment_parameters["leader_probability_stop"]
            ),
            max_questions=assessment_parameters["max_questions"],
            epsilon=assessment_parameters["epsilon"],
            available_problem_type_ids=set(structure_state.graph_artifact.node_ids),
        )
        runtime_snapshot = step_result.runtime
        entropies.append(runtime_snapshot.current_entropy)
        temperatures.append(runtime_snapshot.current_temperature)

        assert np.all(runtime_snapshot.marginal_probabilities >= 0.0)
        assert np.all(runtime_snapshot.marginal_probabilities <= 1.0)
        assert runtime_snapshot.current_entropy >= 0.0
        assert runtime_snapshot.current_entropy <= runtime_snapshot.initial_entropy
        assert runtime_snapshot.current_temperature >= 1.0
        assert 0.0 <= runtime_snapshot.leader_state_probability <= 1.0
        assert len(runtime_snapshot.node_scores) == len(PROBLEM_TYPE_DATA)
        assert len(runtime_snapshot.asked_problem_type_indices) == len(selected_problem_type_ids)

    assert entropies[0] == runtime_snapshot.initial_entropy or entropies[0] > 0.0
    assert temperatures[-1] >= temperatures[0]


@pytest.mark.asyncio
async def test_big_reference_graph_final_result_is_structurally_valid(
    database: DataBase,
    assessment_parameters: AssessmentParameters,
) -> None:
    if database.async_session is None:
        raise RuntimeError("Database session factory is not initialized")

    structure_service = EntranceTestStructureService()

    async with database.async_session() as session:
        await structure_service.compile_current_structure(session)
        structure_state = await structure_service.load_latest_compiled_structure(session)

    runtime_snapshot = initialize_runtime(
        structure_state.forest_artifact,
        assessment_parameters["temperature_sharpening"],
    )

    for answer_index in range(assessment_parameters["max_questions"]):
        selection = select_next_problem_type(
            graph_artifact=structure_state.graph_artifact,
            runtime=runtime_snapshot,
        )
        if selection.problem_type_id is None:
            break

        answer_outcome = (
            Outcome.CORRECT
            if answer_index % 3 == 0
            else Outcome.INCORRECT
            if answer_index % 3 == 1
            else Outcome.I_DONT_KNOW
        )
        step_result = apply_answer_step(
            graph_artifact=structure_state.graph_artifact,
            forest_artifact=structure_state.forest_artifact,
            runtime=runtime_snapshot,
            answered_problem_type_id=selection.problem_type_id,
            outcome=answer_outcome,
            instance_difficulty_weight=1.0,
            i_dont_know_scalar=assessment_parameters["i_dont_know_scalar"],
            ancestor_support_correct=assessment_parameters["ancestor_support_correct"],
            ancestor_support_wrong=assessment_parameters["ancestor_support_wrong"],
            descendant_support_correct=assessment_parameters["descendant_support_correct"],
            descendant_support_wrong=assessment_parameters["descendant_support_wrong"],
            ancestor_decay=assessment_parameters["ancestor_decay"],
            descendant_decay=assessment_parameters["descendant_decay"],
            temperature_sharpening=assessment_parameters["temperature_sharpening"],
            entropy_stop=assessment_parameters["entropy_stop"],
            utility_stop=assessment_parameters["utility_stop"],
            leader_probability_stop=_coerce_optional_float(
                assessment_parameters["leader_probability_stop"]
            ),
            max_questions=assessment_parameters["max_questions"],
            epsilon=assessment_parameters["epsilon"],
            available_problem_type_ids=set(structure_state.graph_artifact.node_ids),
        )
        runtime_snapshot = step_result.runtime
        if step_result.should_stop:
            break

    final_result = build_final_result(
        graph_artifact=structure_state.graph_artifact,
        runtime=runtime_snapshot,
    )
    learned_index_set = set(final_result.learned_problem_type_indices)
    inner_fringe_index_set = set(final_result.inner_fringe_indices)
    outer_fringe_index_set = set(final_result.outer_fringe_indices)

    for node_index in final_result.learned_problem_type_indices:
        assert all(
            prerequisite_index in learned_index_set
            for prerequisite_index in structure_state.graph_artifact.prerequisites_by_index[
                node_index
            ]
        )

    assert inner_fringe_index_set <= learned_index_set
    assert outer_fringe_index_set.isdisjoint(learned_index_set)

    for node_index in final_result.outer_fringe_indices:
        assert all(
            prerequisite_index in learned_index_set
            for prerequisite_index in structure_state.graph_artifact.prerequisites_by_index[
                node_index
            ]
        )

    assert 0.0 <= final_result.state_probability <= 1.0


def _load_optional_float(variable_name: str) -> float | None:
    raw_value = EnvTools.load_env_var(variable_name)
    if not isinstance(raw_value, str) or raw_value == "":
        return None

    return float(raw_value)


def _coerce_optional_float(value: float | int | None) -> float | None:
    if value is None:
        return None

    return float(value)
