from __future__ import annotations

from datetime import UTC, datetime
import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import delete, func, select

from src.config import get_app_config
from src.core.utils import PasswordTools
from src.storage.db.database import DataBase
from src.storage.db.enums import (
    EntranceTestResultNodeStatus,
    EntranceTestStatus,
    EntranceTestStructureStatus,
    ProblemAnswerOptionType,
    UserRole,
)
from src.storage.db.reference_dataset import PROBLEM_TYPE_DATA
from src.fast_api.fastapi_server import create_application
from src.math_models.entrance_assessment import initialize_runtime
from src.models.alchemy import (
    EntranceTestSession,
    EntranceTestStructure,
    Problem,
    ProblemAnswerOption,
    ProblemType,
    ProblemTypePrerequisite,
    ResponseEvent,
    User,
)
from src.services.entrance_test import (
    EntranceTestEvaluatorService,
    EntranceTestProblemPickerService,
    EntranceTestResultProjectionService,
    EntranceTestRuntimeService,
    EntranceTestStructureCompilationFailedError,
    EntranceTestStructureNotCompiledError,
    EntranceTestStructureService,
)
from src.services.problem.loader import build_problem_statement
from src.storage.storage_manager import StorageManager

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


EXPECTED_ROOT_COUNT = 8
EXPECTED_EDGE_COUNT = len(PROBLEM_TYPE_DATA) - EXPECTED_ROOT_COUNT
EXPECTED_FEASIBLE_STATE_COUNT = 8_492_446_687_900_032


def test_create_application_does_not_require_running_event_loop() -> None:
    storage_manager = StorageManager()
    application = create_application(storage_manager)

    assert application is not None
    assert application.state.storage is storage_manager


def test_storage_manager_reuses_sync_and_s3_clients() -> None:
    storage_manager = StorageManager()

    assert storage_manager.get_valkey_sync() is storage_manager.get_valkey_sync()
    assert storage_manager.get_s3_client() is storage_manager.get_s3_client()


@pytest.mark.asyncio
async def test_storage_manager_reuses_async_valkey_client_in_same_loop(
    storage_manager: StorageManager,
) -> None:
    assert storage_manager.get_valkey_async() is storage_manager.get_valkey_async()


@pytest.mark.asyncio
async def test_structure_service_compiles_and_loads_big_reference_structure(
    database: DataBase,
) -> None:
    if database.async_session is None:
        raise RuntimeError("Database session factory is not initialized")

    structure_service = EntranceTestStructureService()

    async with database.async_session() as session:
        compile_response = await structure_service.compile_current_structure(session)
        structure_state = await structure_service.load_latest_compiled_structure(session)
        stored_structure = (
            await session.execute(
                select(EntranceTestStructure).where(
                    EntranceTestStructure.structure_version
                    == compile_response.structure_version
                )
            )
        ).scalar_one()

    assert compile_response.status == EntranceTestStructureStatus.READY
    assert compile_response.artifact_kind == "exact_forest_v1"
    assert compile_response.problem_type_count == len(PROBLEM_TYPE_DATA)
    assert compile_response.edge_count == EXPECTED_EDGE_COUNT
    assert compile_response.feasible_state_count == EXPECTED_FEASIBLE_STATE_COUNT
    assert stored_structure.compiled_payload is not None
    assert structure_state.structure_version == compile_response.structure_version
    assert len(structure_state.graph_artifact.node_ids) == len(PROBLEM_TYPE_DATA)
    assert len(structure_state.forest_artifact.root_indices) == EXPECTED_ROOT_COUNT


@pytest.mark.asyncio
async def test_runtime_service_saves_loads_and_deletes_big_graph_runtime(
    database: DataBase,
) -> None:
    if database.async_session is None:
        raise RuntimeError("Database session factory is not initialized")

    structure_service = EntranceTestStructureService()
    runtime_service = EntranceTestRuntimeService(StorageManager(database))
    temperature_sharpening = float(
        get_app_config().business.require("entrance_assessment.temperature_sharpening")
    )

    async with database.async_session() as session:
        await structure_service.compile_current_structure(session)
        structure_state = await structure_service.load_latest_compiled_structure(session)

    runtime_snapshot = initialize_runtime(
        structure_state.forest_artifact,
        temperature_sharpening,
    )
    entrance_test_session_id = uuid.uuid4()

    await runtime_service.save_runtime_snapshot(
        entrance_test_session_id=entrance_test_session_id,
        structure_version=structure_state.structure_version,
        runtime_snapshot=runtime_snapshot,
    )
    runtime_payload = await runtime_service.load_runtime_payload(entrance_test_session_id)
    loaded_runtime_snapshot = await runtime_service.load_runtime_snapshot(
        entrance_test_session_id
    )

    assert runtime_payload is not None
    assert runtime_payload.runtime_kind == "exact_forest_v1"
    assert runtime_payload.structure_version == structure_state.structure_version
    assert loaded_runtime_snapshot is not None
    assert len(loaded_runtime_snapshot.node_scores) == len(PROBLEM_TYPE_DATA)
    assert len(loaded_runtime_snapshot.marginal_probabilities) == len(PROBLEM_TYPE_DATA)

    await runtime_service.delete_runtime_snapshot(entrance_test_session_id)
    deleted_runtime_payload = await runtime_service.load_runtime_payload(
        entrance_test_session_id
    )

    assert deleted_runtime_payload is None


@pytest.mark.asyncio
async def test_evaluator_service_maps_answer_option_types_to_outcomes_on_reference_problem(
    database: DataBase,
) -> None:
    if database.async_session is None:
        raise RuntimeError("Database session factory is not initialized")

    evaluator_service = EntranceTestEvaluatorService()

    async with database.async_session() as session:
        problem = (
            await session.execute(
                build_problem_statement().order_by(Problem.created_at, Problem.id)
            )
        ).scalars().first()
        assert problem is not None

        right_option = next(
            item for item in problem.answer_options if item.type == ProblemAnswerOptionType.RIGHT
        )
        wrong_option = next(
            item for item in problem.answer_options if item.type == ProblemAnswerOptionType.WRONG
        )
        i_dont_know_option = next(
            item
            for item in problem.answer_options
            if item.type == ProblemAnswerOptionType.I_DONT_KNOW
        )

        right_evaluation = await evaluator_service.evaluate_answer(
            session=session,
            problem_id=problem.id,
            answer_option_id=right_option.id,
        )
        wrong_evaluation = await evaluator_service.evaluate_answer(
            session=session,
            problem_id=problem.id,
            answer_option_id=wrong_option.id,
        )
        i_dont_know_evaluation = await evaluator_service.evaluate_answer(
            session=session,
            problem_id=problem.id,
            answer_option_id=i_dont_know_option.id,
        )

    assert right_evaluation.outcome.value == "correct"
    assert wrong_evaluation.outcome.value == "incorrect"
    assert i_dont_know_evaluation.outcome.value == "i_dont_know"


@pytest.mark.asyncio
async def test_problem_picker_avoids_reusing_reference_problem(
    database: DataBase,
) -> None:
    if database.async_session is None:
        raise RuntimeError("Database session factory is not initialized")

    picker_service = EntranceTestProblemPickerService()

    async with database.async_session() as session:
        row = (
            await session.execute(
                select(Problem.problem_type_id, func.count(Problem.id))
                .group_by(Problem.problem_type_id)
                .having(func.count(Problem.id) >= 2)
                .order_by(Problem.problem_type_id)
            )
        ).first()
        assert row is not None
        problem_type_id = row[0]

        problems = (
            await session.execute(
                build_problem_statement()
                .where(Problem.problem_type_id == problem_type_id)
                .order_by(Problem.created_at, Problem.id)
            )
        ).scalars().all()
        assert len(problems) >= 2

        student = User(
            email=f"picker-{uuid.uuid4().hex}@example.org",
            first_name="Picker",
            last_name="Student",
            avatar_url=None,
            hashed_password=PasswordTools.hash_password("Student123!"),
            role=UserRole.STUDENT,
            is_active=True,
        )
        session.add(student)
        await session.flush()

        entrance_test_session = EntranceTestSession(
            user_id=student.id,
            status=EntranceTestStatus.ACTIVE,
            structure_version=1,
            current_problem_id=problems[0].id,
            started_at=datetime.now(UTC),
        )
        session.add(entrance_test_session)
        await session.flush()

        right_option = next(
            item
            for item in problems[0].answer_options
            if item.type == ProblemAnswerOptionType.RIGHT
        )
        session.add(
            ResponseEvent(
                user_id=student.id,
                problem_id=problems[0].id,
                answer_option_id=right_option.id,
                entrance_test_session_id=entrance_test_session.id,
            )
        )
        await session.flush()

        picked_problem = await picker_service.pick_problem(
            session=session,
            entrance_test_session_id=entrance_test_session.id,
            problem_type_id=problem_type_id,
        )

    assert picked_problem is not None
    assert picked_problem.id == problems[1].id


@pytest.mark.asyncio
async def test_structure_service_requires_compilation_before_loading_latest(
    database: DataBase,
) -> None:
    if database.async_session is None:
        raise RuntimeError("Database session factory is not initialized")

    structure_service = EntranceTestStructureService()

    async with database.async_session() as session:
        await session.execute(delete(EntranceTestStructure))
        await session.commit()
        with pytest.raises(EntranceTestStructureNotCompiledError):
            await structure_service.load_latest_compiled_structure(session)


@pytest.mark.asyncio
async def test_structure_service_fails_when_big_graph_is_no_longer_a_forest(
    database: DataBase,
) -> None:
    if database.async_session is None:
        raise RuntimeError("Database session factory is not initialized")

    structure_service = EntranceTestStructureService()

    async with database.async_session() as session:
        existing_edge = (
            await session.execute(
                select(
                    ProblemTypePrerequisite.problem_type_id,
                    ProblemTypePrerequisite.prerequisite_problem_type_id,
                )
                .order_by(
                    ProblemTypePrerequisite.problem_type_id,
                    ProblemTypePrerequisite.prerequisite_problem_type_id,
                )
            )
        ).first()
        assert existing_edge is not None

        child_problem_type_id = existing_edge[0]
        extra_root_id = (
            await session.execute(
                select(ProblemType.id)
                .where(
                    ~ProblemType.id.in_(
                        select(ProblemTypePrerequisite.problem_type_id)
                    )
                )
                .where(ProblemType.id != existing_edge[1])
                .order_by(ProblemType.id)
            )
        ).scalars().first()
        assert extra_root_id is not None

        session.add(
            ProblemTypePrerequisite(
                problem_type_id=child_problem_type_id,
                prerequisite_problem_type_id=extra_root_id,
            )
        )
        await session.flush()

        compile_response = await structure_service.compile_current_structure(session)

    assert compile_response.status == EntranceTestStructureStatus.FAILED
    assert compile_response.artifact_kind == "exact_forest_v1"
    assert compile_response.error_message == (
        "Entrance test structure must be a forest with at most one prerequisite per problem type"
    )


@pytest.mark.asyncio
async def test_result_projection_service_builds_graph_statuses_and_group_summaries_on_big_graph(
    database: DataBase,
) -> None:
    if database.async_session is None:
        raise RuntimeError("Database session factory is not initialized")

    projection_service = EntranceTestResultProjectionService()

    async with database.async_session() as session:
        root_problem_type = (
            await session.execute(
                select(ProblemType)
                .where(
                    ~ProblemType.id.in_(
                        select(ProblemTypePrerequisite.problem_type_id)
                    )
                )
                .order_by(ProblemType.name, ProblemType.id)
            )
        ).scalars().first()
        assert root_problem_type is not None

        child_problem_type_ids = (
            await session.execute(
                select(ProblemTypePrerequisite.problem_type_id)
                .where(
                    ProblemTypePrerequisite.prerequisite_problem_type_id
                    == root_problem_type.id
                )
                .order_by(ProblemTypePrerequisite.problem_type_id)
            )
        ).scalars().all()
        assert child_problem_type_ids

        student = User(
            email=f"projection-{uuid.uuid4().hex}@example.org",
            first_name="Projection",
            last_name="Student",
            avatar_url=None,
            hashed_password=PasswordTools.hash_password("Student123!"),
            role=UserRole.STUDENT,
            is_active=True,
        )
        session.add(student)
        await session.flush()

        entrance_test_session = EntranceTestSession(
            user_id=student.id,
            status=EntranceTestStatus.COMPLETED,
            structure_version=1,
            current_problem_id=None,
            final_state_index=123,
            final_state_probability=0.88,
            learned_problem_type_ids=[root_problem_type.id],
            inner_fringe_problem_type_ids=[root_problem_type.id],
            outer_fringe_problem_type_ids=list(child_problem_type_ids),
            completed_at=datetime.now(UTC),
        )
        session.add(entrance_test_session)
        await session.flush()

        result_payload = await projection_service.build_result(
            session=session,
            entrance_test_session=entrance_test_session,
        )

    learned_node = next(
        node for node in result_payload.nodes if node.id == root_problem_type.id
    )
    ready_nodes = [
        node for node in result_payload.nodes if node.id in set(child_problem_type_ids)
    ]

    assert learned_node.status == EntranceTestResultNodeStatus.LEARNED
    assert learned_node.is_frontier is True
    assert ready_nodes
    assert all(node.status == EntranceTestResultNodeStatus.READY for node in ready_nodes)
    assert result_payload.edges
    assert result_payload.topic_summaries
    assert result_payload.subtopic_summaries
