from __future__ import annotations

from typing import TypedDict

import numpy as np
import pytest

from src.config import get_app_config
from src.storage.db.database import DataBase
from src.storage.db.reference_dataset import PROBLEM_TYPE_DATA
from src.math_models.entrance_assessment import (
    Outcome,
    apply_answer_step,
    build_final_result,
    initialize_runtime,
    select_next_problem_type,
)
from src.models.pydantic import ResponseModel
from src.services.entrance_test import EntranceTestStructureService


EXPECTED_ROOT_COUNT = 8
EXPECTED_EDGE_COUNT = len(PROBLEM_TYPE_DATA) - EXPECTED_ROOT_COUNT
EXPECTED_FEASIBLE_STATE_COUNT = 8_492_446_687_900_032


class AssessmentParameters(TypedDict):
    i_dont_know_scalar: float
    temperature_sharpening: float
    projected_learned_mastery_probability: float
    projected_unlearned_mastery_probability: float
    projection_confidence_stop: float
    frontier_confidence_stop: float
    entropy_stop: float
    utility_stop: float
    leader_probability_stop: float | None
    max_questions: int


@pytest.fixture(scope="module")
def assessment_parameters() -> AssessmentParameters:
    config = get_app_config().business
    return AssessmentParameters(
        i_dont_know_scalar=float(config.require("entrance_assessment.i_dont_know_scalar")),
        temperature_sharpening=float(
            config.require("entrance_assessment.temperature_sharpening")
        ),
        projected_learned_mastery_probability=float(
            config.require(
                "entrance_assessment.projected_learned_mastery_probability"
            )
        ),
        projected_unlearned_mastery_probability=float(
            config.require(
                "entrance_assessment.projected_unlearned_mastery_probability"
            )
        ),
        projection_confidence_stop=float(
            config.require("entrance_assessment.projection_confidence_stop")
        ),
        frontier_confidence_stop=float(
            config.require("entrance_assessment.frontier_confidence_stop")
        ),
        entropy_stop=float(config.require("entrance_assessment.entropy_stop")),
        utility_stop=float(config.require("entrance_assessment.utility_stop")),
        leader_probability_stop=_load_optional_float(
            config.get("entrance_assessment.leader_probability_stop")
        ),
        max_questions=int(config.require("entrance_assessment.max_questions")),
    )


@pytest.fixture(scope="module")
def response_model() -> ResponseModel:
    config = get_app_config().business
    return ResponseModel(
        mastered_right=float(
            config.require("entrance_assessment.response_model.mastered_right")
        ),
        mastered_wrong=float(
            config.require("entrance_assessment.response_model.mastered_wrong")
        ),
        mastered_i_dont_know=float(
            config.require("entrance_assessment.response_model.mastered_i_dont_know")
        ),
        unmastered_right=float(
            config.require("entrance_assessment.response_model.unmastered_right")
        ),
        unmastered_wrong=float(
            config.require("entrance_assessment.response_model.unmastered_wrong")
        ),
        unmastered_i_dont_know=float(
            config.require("entrance_assessment.response_model.unmastered_i_dont_know")
        ),
    )


@pytest.mark.asyncio
async def test_big_reference_graph_compiles_to_exact_bayesian_forest_runtime(
    database: DataBase,
) -> None:
    if database.async_session is None:
        raise RuntimeError("Database session factory is not initialized")

    structure_service = EntranceTestStructureService()

    async with database.async_session() as session:
        compile_response = await structure_service.compile_current_structure(session)
        structure_state = await structure_service.load_latest_compiled_structure(session)

    assert compile_response.status == "ready"
    assert compile_response.artifact_kind == "exact_forest_bayes_v2"
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
    response_model: ResponseModel,
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
    utilities: list[float] = []

    for answer_outcome in answer_outcomes:
        selection = select_next_problem_type(
            graph_artifact=structure_state.graph_artifact,
            runtime=runtime_snapshot,
            learned_mastery_probability=assessment_parameters[
                "projected_learned_mastery_probability"
            ],
            unlearned_mastery_probability=assessment_parameters[
                "projected_unlearned_mastery_probability"
            ],
        )
        assert selection.problem_type_id is not None
        assert selection.problem_type_id not in selected_problem_type_ids
        selected_problem_type_ids.append(selection.problem_type_id)
        utilities.append(selection.max_utility)

        step_result = apply_answer_step(
            graph_artifact=structure_state.graph_artifact,
            forest_artifact=structure_state.forest_artifact,
            runtime=runtime_snapshot,
            answered_problem_type_id=selection.problem_type_id,
            outcome=answer_outcome,
            instance_difficulty_weight=1.0,
            response_model=response_model,
            i_dont_know_scalar=assessment_parameters["i_dont_know_scalar"],
            temperature_sharpening=assessment_parameters["temperature_sharpening"],
            entropy_stop=assessment_parameters["entropy_stop"],
            utility_stop=assessment_parameters["utility_stop"],
            leader_probability_stop=assessment_parameters["leader_probability_stop"],
            max_questions=assessment_parameters["max_questions"],
            available_problem_type_ids=set(structure_state.graph_artifact.node_ids),
            learned_mastery_probability=assessment_parameters[
                "projected_learned_mastery_probability"
            ],
            unlearned_mastery_probability=assessment_parameters[
                "projected_unlearned_mastery_probability"
            ],
            projection_confidence_stop=assessment_parameters[
                "projection_confidence_stop"
            ],
            frontier_confidence_stop=assessment_parameters[
                "frontier_confidence_stop"
            ],
        )
        runtime_snapshot = step_result.runtime
        entropies.append(runtime_snapshot.current_entropy)

        assert np.all(runtime_snapshot.marginal_probabilities >= 0.0)
        assert np.all(runtime_snapshot.marginal_probabilities <= 1.0)
        assert runtime_snapshot.current_entropy >= 0.0
        assert runtime_snapshot.current_entropy <= runtime_snapshot.initial_entropy
        assert 0.0 <= runtime_snapshot.normalized_entropy <= 1.0
        assert runtime_snapshot.current_temperature >= 1.0
        assert 0.0 <= runtime_snapshot.leader_state_probability <= 1.0
        assert len(runtime_snapshot.node_scores) == len(PROBLEM_TYPE_DATA)
        assert len(runtime_snapshot.asked_problem_type_indices) == len(selected_problem_type_ids)

    assert entropies[0] > entropies[-1]
    assert any(utility > 0.0 for utility in utilities)


@pytest.mark.asyncio
async def test_big_reference_graph_selection_prefers_projected_outer_fringe(
    database: DataBase,
    assessment_parameters: AssessmentParameters,
    response_model: ResponseModel,
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

    for answer_outcome in (Outcome.CORRECT, Outcome.CORRECT, Outcome.INCORRECT):
        selection = select_next_problem_type(
            graph_artifact=structure_state.graph_artifact,
            runtime=runtime_snapshot,
            learned_mastery_probability=assessment_parameters[
                "projected_learned_mastery_probability"
            ],
            unlearned_mastery_probability=assessment_parameters[
                "projected_unlearned_mastery_probability"
            ],
        )
        assert selection.problem_type_id is not None

        step_result = apply_answer_step(
            graph_artifact=structure_state.graph_artifact,
            forest_artifact=structure_state.forest_artifact,
            runtime=runtime_snapshot,
            answered_problem_type_id=selection.problem_type_id,
            outcome=answer_outcome,
            instance_difficulty_weight=1.0,
            response_model=response_model,
            i_dont_know_scalar=assessment_parameters["i_dont_know_scalar"],
            temperature_sharpening=assessment_parameters["temperature_sharpening"],
            entropy_stop=assessment_parameters["entropy_stop"],
            utility_stop=assessment_parameters["utility_stop"],
            leader_probability_stop=assessment_parameters["leader_probability_stop"],
            max_questions=assessment_parameters["max_questions"],
            available_problem_type_ids=set(structure_state.graph_artifact.node_ids),
            learned_mastery_probability=assessment_parameters[
                "projected_learned_mastery_probability"
            ],
            unlearned_mastery_probability=assessment_parameters[
                "projected_unlearned_mastery_probability"
            ],
            projection_confidence_stop=assessment_parameters[
                "projection_confidence_stop"
            ],
            frontier_confidence_stop=assessment_parameters[
                "frontier_confidence_stop"
            ],
        )
        runtime_snapshot = step_result.runtime

    final_result = build_final_result(
        graph_artifact=structure_state.graph_artifact,
        runtime=runtime_snapshot,
        learned_mastery_probability=assessment_parameters[
            "projected_learned_mastery_probability"
        ],
        unlearned_mastery_probability=assessment_parameters[
            "projected_unlearned_mastery_probability"
        ],
    )
    outer_fringe_ids = set(final_result.outer_fringe_ids)

    selection = select_next_problem_type(
        graph_artifact=structure_state.graph_artifact,
        runtime=runtime_snapshot,
        learned_mastery_probability=assessment_parameters[
            "projected_learned_mastery_probability"
        ],
        unlearned_mastery_probability=assessment_parameters[
            "projected_unlearned_mastery_probability"
        ],
    )

    assert selection.problem_type_id is not None
    assert outer_fringe_ids
    assert selection.problem_type_id in outer_fringe_ids


@pytest.mark.asyncio
async def test_big_reference_graph_final_result_is_structurally_valid(
    database: DataBase,
    assessment_parameters: AssessmentParameters,
    response_model: ResponseModel,
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
            learned_mastery_probability=assessment_parameters[
                "projected_learned_mastery_probability"
            ],
            unlearned_mastery_probability=assessment_parameters[
                "projected_unlearned_mastery_probability"
            ],
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
            response_model=response_model,
            i_dont_know_scalar=assessment_parameters["i_dont_know_scalar"],
            temperature_sharpening=assessment_parameters["temperature_sharpening"],
            entropy_stop=assessment_parameters["entropy_stop"],
            utility_stop=assessment_parameters["utility_stop"],
            leader_probability_stop=assessment_parameters["leader_probability_stop"],
            max_questions=assessment_parameters["max_questions"],
            available_problem_type_ids=set(structure_state.graph_artifact.node_ids),
            learned_mastery_probability=assessment_parameters[
                "projected_learned_mastery_probability"
            ],
            unlearned_mastery_probability=assessment_parameters[
                "projected_unlearned_mastery_probability"
            ],
            projection_confidence_stop=assessment_parameters[
                "projection_confidence_stop"
            ],
            frontier_confidence_stop=assessment_parameters[
                "frontier_confidence_stop"
            ],
        )
        runtime_snapshot = step_result.runtime
        if step_result.should_stop:
            break

    final_result = build_final_result(
        graph_artifact=structure_state.graph_artifact,
        runtime=runtime_snapshot,
        learned_mastery_probability=assessment_parameters[
            "projected_learned_mastery_probability"
        ],
        unlearned_mastery_probability=assessment_parameters[
            "projected_unlearned_mastery_probability"
        ],
    )
    learned_problem_type_ids = set(final_result.learned_problem_type_ids)
    inner_fringe_ids = set(final_result.inner_fringe_ids)
    outer_fringe_ids = set(final_result.outer_fringe_ids)

    for learned_problem_type_id in final_result.learned_problem_type_ids:
        node_index = structure_state.graph_artifact.index_by_id[learned_problem_type_id]
        assert all(
            structure_state.graph_artifact.node_ids[prerequisite_index]
            in learned_problem_type_ids
            for prerequisite_index in structure_state.graph_artifact.prerequisites_by_index[
                node_index
            ]
        )

    assert inner_fringe_ids <= learned_problem_type_ids
    assert outer_fringe_ids.isdisjoint(learned_problem_type_ids)
    assert inner_fringe_ids.isdisjoint(outer_fringe_ids)

    for outer_problem_type_id in final_result.outer_fringe_ids:
        node_index = structure_state.graph_artifact.index_by_id[outer_problem_type_id]
        assert all(
            structure_state.graph_artifact.node_ids[prerequisite_index]
            in learned_problem_type_ids
            for prerequisite_index in structure_state.graph_artifact.prerequisites_by_index[
                node_index
            ]
        )

    assert 0.0 <= final_result.state_probability <= 1.0
    assert len(final_result.learned_problem_type_ids) > 0
    assert len(final_result.outer_fringe_ids) > 0


def _load_optional_float(raw_value: float | int | None) -> float | None:
    if raw_value is None:
        return None

    return float(raw_value)
