from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy import Select, select

from src.config import get_app_config
from src.storage.db.enums import EntranceTestStatus, ProblemAnswerOptionType, UserRole
from src.math_models.entrance_assessment import (
    Outcome,
    apply_answer_step,
    build_final_result,
    initialize_runtime,
    select_next_problem_type,
    should_stop,
)
from src.models.alchemy import (
    EntranceTestSession,
    Problem,
    ResponseEvent,
    User,
)
from src.models.pydantic import (
    EntranceTestAnswerRequest,
    EntranceTestAnswerResponse,
    EntranceTestStructureCompileResponse,
    EntranceTestCurrentProblemResponse,
    EntranceTestFinalResultResponse,
    EntranceTestResultResponse,
    EntranceTestRuntimePayload,
    EntranceTestSessionResponse,
    ResponseModel,
    ResponseCreate,
    StoredEntranceTestAnswerState,
    build_entrance_test_final_result_response,
    build_entrance_test_session_response,
)
from src.services.entrance_test.evaluator_service import EntranceTestEvaluatorService
from src.services.entrance_test.problem_picker_service import EntranceTestProblemPickerService
from src.services.entrance_test.result_projection_service import (
    EntranceTestResultProjectionService,
)
from src.services.entrance_test.runtime_service import EntranceTestRuntimeService
from src.services.entrance_test.structure_service import (
    EntranceTestStructureCompilationFailedError,
    EntranceTestStructureNotCompiledError,
    EntranceTestStructureService,
)
from src.services.problem.loader import load_problem_or_404
from src.services.problem.mapper import build_problem_response
from src.services.response import ResponseRecorderService
from src.storage.storage_manager import StorageManager
from src.transaction_manager.transaction_manager import execute_atomic_step, transactional

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.models.pydantic import EntranceTestStructureState, RuntimeSnapshot


class EntranceTestService:
    def __init__(self, storage_manager: StorageManager) -> None:
        self.storage_manager = storage_manager
        self.structure_service = EntranceTestStructureService()
        self.runtime_service = EntranceTestRuntimeService(storage_manager)
        self.evaluator_service = EntranceTestEvaluatorService()
        self.problem_picker_service = EntranceTestProblemPickerService()
        self.result_projection_service = EntranceTestResultProjectionService()
        self.response_recorder_service = ResponseRecorderService()


    async def create_pending_session_in_session(
        self,
        session: "AsyncSession",
        user: User,
    ) -> EntranceTestSession | None:
        if user.role != UserRole.STUDENT:
            return None

        entrance_test_session = EntranceTestSession(
            user=user,
            status=EntranceTestStatus.PENDING,
            structure_version=1,
            current_problem_id=None,
            learned_problem_type_ids=[],
            inner_fringe_problem_type_ids=[],
            outer_fringe_problem_type_ids=[],
            business_config_snapshot=None,
        )
        session.add(entrance_test_session)
        await session.flush()
        user.entrance_test_session = entrance_test_session
        return entrance_test_session


    async def get_session(self, user_id: uuid.UUID) -> EntranceTestSessionResponse:
        async with self.storage_manager.session_ctx() as session:
            entrance_test_session = await self._load_session(session, user_id)
            return build_entrance_test_session_response(entrance_test_session)


    async def get_result(self, user_id: uuid.UUID) -> EntranceTestResultResponse:
        async with self.storage_manager.session_ctx() as session:
            entrance_test_session = await self._load_session(session, user_id)
            if entrance_test_session.status != EntranceTestStatus.COMPLETED:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Entrance test result is available only for completed sessions",
                )

            if entrance_test_session.final_state_index is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Entrance test result is not stored for this session",
                )

            return await self.result_projection_service.build_result(
                session,
                entrance_test_session,
            )


    async def compile_current_structure(self) -> EntranceTestStructureCompileResponse:
        async with self.storage_manager.session_ctx() as session:
            try:
                return await self.structure_service.compile_current_structure(session)
            except ValueError as error:
                logger.warning("Cannot compile entrance test structure: {}", error)
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=str(error),
                ) from error


    async def start_session(self, user_id: uuid.UUID) -> EntranceTestCurrentProblemResponse:
        async with self.storage_manager.session_ctx() as session:
            entrance_test_session = await self._load_session(session, user_id, lock=True)
            if entrance_test_session.status == EntranceTestStatus.SKIPPED:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Entrance test has already been skipped",
                )
            if entrance_test_session.status == EntranceTestStatus.COMPLETED:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Entrance test has already been completed",
                )

            current_problem: Problem | None
            if entrance_test_session.status == EntranceTestStatus.PENDING:
                entrance_test_session.business_config_snapshot = get_app_config().business_snapshot()
                structure_state = await self._load_latest_structure_state(session)
                assessment_config = self._get_assessment_config(entrance_test_session)
                runtime_snapshot = initialize_runtime(
                    structure_state.forest_artifact,
                    float(assessment_config["temperature_sharpening"]),
                )
                self._clear_final_result(entrance_test_session)
                entrance_test_session.structure_version = structure_state.structure_version
                entrance_test_session.started_at = datetime.now(UTC)
                entrance_test_session.completed_at = None
                current_problem = await self._select_current_problem(
                    session=session,
                    entrance_test_session=entrance_test_session,
                    structure_state=structure_state,
                    runtime_snapshot=runtime_snapshot,
                )
            elif entrance_test_session.current_problem_id is None:
                structure_state = await self._load_session_structure_state(
                    session=session,
                    structure_version=entrance_test_session.structure_version,
                )
                runtime_snapshot = await self._load_or_rebuild_runtime(
                    session=session,
                    entrance_test_session=entrance_test_session,
                    structure_state=structure_state,
                )
                current_problem = await self._select_current_problem(
                    session=session,
                    entrance_test_session=entrance_test_session,
                    structure_state=structure_state,
                    runtime_snapshot=runtime_snapshot,
                )
            else:
                current_problem = await self._load_current_problem(session, entrance_test_session)

            logger.info(
                "Started entrance test session: session_id={}, user_id={}, structure_version={}, current_problem_id={}",
                entrance_test_session.id,
                user_id,
                entrance_test_session.structure_version,
                entrance_test_session.current_problem_id,
            )
            session_response = build_entrance_test_session_response(entrance_test_session)

        return EntranceTestCurrentProblemResponse(
            session=session_response,
            problem=(
                build_problem_response(current_problem)
                if current_problem is not None
                else None
            ),
        )


    async def get_current_problem(self, user_id: uuid.UUID) -> EntranceTestCurrentProblemResponse:
        async with self.storage_manager.session_ctx() as session:
            entrance_test_session = await self._load_session(session, user_id)
            session_response = build_entrance_test_session_response(entrance_test_session)
            current_problem = await self._load_optional_current_problem(
                session,
                entrance_test_session,
            )

        return EntranceTestCurrentProblemResponse(
            session=session_response,
            problem=(
                build_problem_response(current_problem)
                if current_problem is not None
                else None
            ),
        )


    @transactional
    async def submit_answer(
        self,
        user_id: uuid.UUID,
        data: EntranceTestAnswerRequest,
    ) -> EntranceTestAnswerResponse:
        stored_state = await execute_atomic_step(
            action=lambda: self._store_session_answer(user_id, data),
            rollback=self._rollback_session_answer,
            step_name="store_entrance_test_answer",
        )
        return EntranceTestAnswerResponse(
            session=stored_state.session,
            response=stored_state.response_state,
            next_problem=stored_state.next_problem,
            final_result=stored_state.final_result,
        )


    async def skip_session(self, user_id: uuid.UUID) -> EntranceTestSessionResponse:
        async with self.storage_manager.session_ctx() as session:
            entrance_test_session = await self._load_session(session, user_id, lock=True)
            if entrance_test_session.status == EntranceTestStatus.COMPLETED:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Completed entrance test cannot be skipped",
                )

            if entrance_test_session.status != EntranceTestStatus.SKIPPED:
                entrance_test_session.status = EntranceTestStatus.SKIPPED
                entrance_test_session.current_problem_id = None
                entrance_test_session.skipped_at = datetime.now(UTC)
                self._clear_final_result(entrance_test_session)
                await self.runtime_service.delete_runtime_snapshot(entrance_test_session.id)
                logger.info(
                    "Skipped entrance test session: session_id={}, user_id={}",
                    entrance_test_session.id,
                    user_id,
                )

            return build_entrance_test_session_response(entrance_test_session)


    async def complete_session(self, user_id: uuid.UUID) -> EntranceTestSessionResponse:
        async with self.storage_manager.session_ctx() as session:
            entrance_test_session = await self._load_session(session, user_id, lock=True)
            if entrance_test_session.status == EntranceTestStatus.SKIPPED:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Skipped entrance test cannot be completed",
                )

            if entrance_test_session.current_problem_id is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Entrance test is not finished yet",
                )

            if entrance_test_session.status != EntranceTestStatus.COMPLETED:
                entrance_test_session.status = EntranceTestStatus.COMPLETED
                entrance_test_session.completed_at = datetime.now(UTC)
                await self.runtime_service.delete_runtime_snapshot(entrance_test_session.id)
                logger.info(
                    "Completed entrance test session: session_id={}, user_id={}",
                    entrance_test_session.id,
                    user_id,
                )

            return build_entrance_test_session_response(entrance_test_session)


    async def _store_session_answer(
        self,
        user_id: uuid.UUID,
        data: EntranceTestAnswerRequest,
    ) -> StoredEntranceTestAnswerState:
        async with self.storage_manager.session_ctx() as session:
            entrance_test_session = await self._load_session(session, user_id, lock=True)
            if entrance_test_session.status != EntranceTestStatus.ACTIVE:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Entrance test is not active",
                )

            current_problem_id = entrance_test_session.current_problem_id
            if current_problem_id is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Entrance test does not have a current problem",
                )

            if data.problem_id != current_problem_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Submitted problem does not match the current entrance test problem",
                )

            structure_state = await self._load_session_structure_state(
                session=session,
                structure_version=entrance_test_session.structure_version,
            )

            previous_status = entrance_test_session.status
            previous_current_problem_id = entrance_test_session.current_problem_id
            previous_completed_at = entrance_test_session.completed_at
            previous_final_result = build_entrance_test_session_response(
                entrance_test_session
            ).final_result
            previous_runtime_payload = await self.runtime_service.load_runtime_payload(
                entrance_test_session.id
            )
            runtime_snapshot = await self._load_or_rebuild_runtime(
                session=session,
                entrance_test_session=entrance_test_session,
                structure_state=structure_state,
                runtime_payload=previous_runtime_payload,
            )
            assessment_config = self._get_assessment_config(entrance_test_session)
            evaluation_state = await self.evaluator_service.evaluate_answer(
                session=session,
                problem_id=data.problem_id,
                answer_option_id=data.answer_option_id,
            )
            response_state = await self.response_recorder_service.record_response(
                session,
                user_id,
                ResponseCreate(
                    problem_id=data.problem_id,
                    answer_option_id=data.answer_option_id,
                    entrance_test_session_id=entrance_test_session.id,
                    problem_type_id=evaluation_state.problem_type_id,
                    answer_option_type=evaluation_state.answer_option_type,
                    difficulty=evaluation_state.difficulty,
                    difficulty_weight=evaluation_state.difficulty_weight,
                ),
            )
            step_result = apply_answer_step(
                graph_artifact=structure_state.graph_artifact,
                forest_artifact=structure_state.forest_artifact,
                runtime=runtime_snapshot,
                answered_problem_type_id=evaluation_state.problem_type_id,
                outcome=evaluation_state.outcome,
                instance_difficulty_weight=evaluation_state.difficulty_weight,
                response_model=self._build_response_model(assessment_config),
                i_dont_know_scalar=float(assessment_config["i_dont_know_scalar"]),
                temperature_sharpening=float(assessment_config["temperature_sharpening"]),
                entropy_stop=float(assessment_config["entropy_stop"]),
                utility_stop=float(assessment_config["utility_stop"]),
                leader_probability_stop=self._coerce_optional_float(
                    assessment_config.get("leader_probability_stop")
                ),
                max_questions=int(assessment_config["max_questions"]),
                available_problem_type_ids=set(structure_state.graph_artifact.node_ids),
                learned_mastery_probability=self._get_projected_learned_mastery_probability(
                    assessment_config
                ),
                unlearned_mastery_probability=self._get_projected_unlearned_mastery_probability(
                    assessment_config
                ),
                projection_confidence_stop=self._get_projection_confidence_stop(
                    assessment_config
                ),
                frontier_confidence_stop=self._get_frontier_confidence_stop(
                    assessment_config
                ),
            )
            await self.runtime_service.save_runtime_snapshot(
                entrance_test_session.id,
                structure_state.structure_version,
                step_result.runtime,
            )

            next_problem: Problem | None = None
            next_problem_response = None
            final_result_response = None

            if step_result.should_stop or step_result.selection.problem_type_id is None:
                final_result = build_final_result(
                    graph_artifact=structure_state.graph_artifact,
                    runtime=step_result.runtime,
                    learned_mastery_probability=self._get_projected_learned_mastery_probability(
                        assessment_config
                    ),
                    unlearned_mastery_probability=self._get_projected_unlearned_mastery_probability(
                        assessment_config
                    ),
                )
                final_result_response = build_entrance_test_final_result_response(
                    final_result
                )
                self._persist_final_result(
                    entrance_test_session,
                    final_result_response=final_result_response,
                )
                entrance_test_session.status = EntranceTestStatus.COMPLETED
                entrance_test_session.current_problem_id = None
                entrance_test_session.completed_at = datetime.now(UTC)
                logger.info(
                    "Persisted completed entrance test result after answer: session_id={}, state_index={}, confidence={}, learned_count={}, inner_fringe_count={}, outer_fringe_count={}",
                    entrance_test_session.id,
                    final_result_response.state_index,
                    final_result_response.state_probability,
                    len(final_result_response.learned_problem_type_ids),
                    len(final_result_response.inner_fringe_ids),
                    len(final_result_response.outer_fringe_ids),
                )
                await self.runtime_service.delete_runtime_snapshot(
                    entrance_test_session.id
                )
            else:
                next_problem = await self.problem_picker_service.pick_problem(
                    session=session,
                    entrance_test_session_id=entrance_test_session.id,
                    problem_type_id=step_result.selection.problem_type_id,
                )
                if next_problem is None:
                    final_result = build_final_result(
                        graph_artifact=structure_state.graph_artifact,
                        runtime=step_result.runtime,
                        learned_mastery_probability=self._get_projected_learned_mastery_probability(
                            assessment_config
                        ),
                        unlearned_mastery_probability=self._get_projected_unlearned_mastery_probability(
                            assessment_config
                        ),
                    )
                    final_result_response = build_entrance_test_final_result_response(
                        final_result
                    )
                    self._persist_final_result(
                        entrance_test_session,
                        final_result_response=final_result_response,
                    )
                    entrance_test_session.status = EntranceTestStatus.COMPLETED
                    entrance_test_session.current_problem_id = None
                    entrance_test_session.completed_at = datetime.now(UTC)
                    logger.info(
                        "Persisted completed entrance test result after exhausted problems: session_id={}, state_index={}, confidence={}, learned_count={}, inner_fringe_count={}, outer_fringe_count={}",
                        entrance_test_session.id,
                        final_result_response.state_index,
                        final_result_response.state_probability,
                        len(final_result_response.learned_problem_type_ids),
                        len(final_result_response.inner_fringe_ids),
                        len(final_result_response.outer_fringe_ids),
                    )
                    await self.runtime_service.delete_runtime_snapshot(
                        entrance_test_session.id
                    )
                else:
                    self._clear_final_result(entrance_test_session)
                    entrance_test_session.current_problem_id = next_problem.id
                    next_problem_response = build_problem_response(next_problem)

            logger.info(
                "Recorded entrance test answer: session_id={}, problem_id={}, problem_type_id={}, answer_option_type={}, next_problem_id={}, status={}, entropy={}, utility={}, stop_reason={}",
                entrance_test_session.id,
                data.problem_id,
                evaluation_state.problem_type_id,
                evaluation_state.answer_option_type,
                entrance_test_session.current_problem_id,
                entrance_test_session.status,
                step_result.runtime.current_entropy,
                step_result.selection.max_utility,
                step_result.stop_reason,
            )

            return StoredEntranceTestAnswerState(
                session_id=entrance_test_session.id,
                previous_status=previous_status,
                previous_current_problem_id=previous_current_problem_id,
                previous_completed_at=previous_completed_at,
                previous_final_result=previous_final_result,
                previous_runtime_payload=previous_runtime_payload,
                session=build_entrance_test_session_response(entrance_test_session),
                response_state=response_state,
                next_problem=next_problem_response,
                final_result=final_result_response,
            )


    async def _rollback_session_answer(
        self,
        stored_state: StoredEntranceTestAnswerState,
    ) -> None:
        async with self.storage_manager.session_ctx() as session:
            response_event = await session.get(
                ResponseEvent,
                stored_state.response_state.response_id,
            )
            if response_event is not None:
                await session.delete(response_event)

            entrance_test_session = await session.get(
                EntranceTestSession,
                stored_state.session_id,
            )
            if entrance_test_session is not None:
                entrance_test_session.status = stored_state.previous_status
                entrance_test_session.current_problem_id = (
                    stored_state.previous_current_problem_id
                )
                entrance_test_session.completed_at = stored_state.previous_completed_at
                self._restore_final_result(
                    entrance_test_session,
                    stored_state.previous_final_result,
                )

        if stored_state.previous_runtime_payload is None:
            await self.runtime_service.delete_runtime_snapshot(stored_state.session_id)
        else:
            runtime_snapshot = self.runtime_service.build_runtime_snapshot(
                stored_state.previous_runtime_payload
            )
            await self.runtime_service.save_runtime_snapshot(
                stored_state.session_id,
                stored_state.previous_runtime_payload.structure_version,
                runtime_snapshot,
            )


    async def _load_session(
        self,
        session: "AsyncSession",
        user_id: uuid.UUID,
        *,
        lock: bool = False,
    ) -> EntranceTestSession:
        statement: Select[tuple[EntranceTestSession]] = select(EntranceTestSession).where(
            EntranceTestSession.user_id == user_id
        )
        if lock:
            statement = statement.with_for_update()

        result = await session.execute(statement)
        entrance_test_session = result.scalar_one_or_none()
        if entrance_test_session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Entrance test session not found",
            )
        return entrance_test_session


    async def _load_current_problem(
        self,
        session: "AsyncSession",
        entrance_test_session: EntranceTestSession,
    ) -> Problem:
        current_problem_id = entrance_test_session.current_problem_id
        if current_problem_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Entrance test does not have a current problem",
            )
        return await load_problem_or_404(session, current_problem_id)


    async def _load_optional_current_problem(
        self,
        session: "AsyncSession",
        entrance_test_session: EntranceTestSession,
    ) -> Problem | None:
        current_problem_id = entrance_test_session.current_problem_id
        if current_problem_id is None:
            return None

        return await load_problem_or_404(session, current_problem_id)


    async def _load_latest_structure_state(
        self,
        session: "AsyncSession",
    ) -> "EntranceTestStructureState":
        try:
            return await self.structure_service.ensure_latest_compiled_structure(session)
        except (
            ValueError,
            EntranceTestStructureNotCompiledError,
            EntranceTestStructureCompilationFailedError,
        ) as error:
            logger.warning("Cannot load latest entrance test structure: {}", error)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error


    async def _load_session_structure_state(
        self,
        session: "AsyncSession",
        structure_version: int,
    ) -> "EntranceTestStructureState":
        try:
            return await self.structure_service.load_compiled_structure(
                session=session,
                structure_version=structure_version,
            )
        except (
            EntranceTestStructureNotCompiledError,
            EntranceTestStructureCompilationFailedError,
        ) as error:
            logger.warning(
                "Cannot load entrance test structure for session version {}: {}",
                structure_version,
                error,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error


    async def _select_current_problem(
        self,
        session: "AsyncSession",
        entrance_test_session: EntranceTestSession,
        structure_state: "EntranceTestStructureState",
        runtime_snapshot: "RuntimeSnapshot",
    ) -> Problem | None:
        assessment_config = self._get_assessment_config(entrance_test_session)
        selection = select_next_problem_type(
            graph_artifact=structure_state.graph_artifact,
            runtime=runtime_snapshot,
            learned_mastery_probability=self._get_projected_learned_mastery_probability(
                assessment_config
            ),
            unlearned_mastery_probability=self._get_projected_unlearned_mastery_probability(
                assessment_config
            ),
        )
        stop, stop_reason = should_stop(
            graph_artifact=structure_state.graph_artifact,
            runtime=runtime_snapshot,
            selection=selection,
            entropy_stop=float(assessment_config["entropy_stop"]),
            utility_stop=float(assessment_config["utility_stop"]),
            leader_probability_stop=self._coerce_optional_float(
                assessment_config.get("leader_probability_stop")
            ),
            max_questions=int(assessment_config["max_questions"]),
            learned_mastery_probability=self._get_projected_learned_mastery_probability(
                assessment_config
            ),
            unlearned_mastery_probability=self._get_projected_unlearned_mastery_probability(
                assessment_config
            ),
            projection_confidence_stop=self._get_projection_confidence_stop(
                assessment_config
            ),
            frontier_confidence_stop=self._get_frontier_confidence_stop(
                assessment_config
            ),
        )
        logger.info(
            "Selected entrance test current problem: session_id={}, structure_version={}, entropy={}, utility={}, stop_reason={}, selected_problem_type_id={}",
            entrance_test_session.id,
            structure_state.structure_version,
            runtime_snapshot.current_entropy,
            selection.max_utility,
            stop_reason,
            selection.problem_type_id,
        )

        if stop or selection.problem_type_id is None:
            final_result = build_final_result(
                graph_artifact=structure_state.graph_artifact,
                runtime=runtime_snapshot,
                learned_mastery_probability=self._get_projected_learned_mastery_probability(
                    assessment_config
                ),
                unlearned_mastery_probability=self._get_projected_unlearned_mastery_probability(
                    assessment_config
                ),
            )
            final_result_response = build_entrance_test_final_result_response(final_result)
            self._persist_final_result(
                entrance_test_session,
                final_result_response=final_result_response,
            )
            entrance_test_session.status = EntranceTestStatus.COMPLETED
            entrance_test_session.current_problem_id = None
            entrance_test_session.completed_at = datetime.now(UTC)
            await self.runtime_service.delete_runtime_snapshot(entrance_test_session.id)
            logger.info(
                "Persisted completed entrance test result at session transition: session_id={}, state_index={}, confidence={}, learned_count={}, inner_fringe_count={}, outer_fringe_count={}",
                entrance_test_session.id,
                final_result_response.state_index,
                final_result_response.state_probability,
                len(final_result_response.learned_problem_type_ids),
                len(final_result_response.inner_fringe_ids),
                len(final_result_response.outer_fringe_ids),
            )
            return None

        current_problem = await self.problem_picker_service.pick_problem(
            session=session,
            entrance_test_session_id=entrance_test_session.id,
            problem_type_id=selection.problem_type_id,
        )
        if current_problem is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Entrance test does not have available problems",
            )

        entrance_test_session.status = EntranceTestStatus.ACTIVE
        entrance_test_session.current_problem_id = current_problem.id
        entrance_test_session.completed_at = None
        await self.runtime_service.save_runtime_snapshot(
            entrance_test_session.id,
            structure_state.structure_version,
            runtime_snapshot,
        )
        return current_problem


    async def _load_or_rebuild_runtime(
        self,
        session: "AsyncSession",
        entrance_test_session: EntranceTestSession,
        structure_state: "EntranceTestStructureState",
        runtime_payload: EntranceTestRuntimePayload | None = None,
    ) -> "RuntimeSnapshot":
        if runtime_payload is None:
            runtime_payload = await self.runtime_service.load_runtime_payload(
                entrance_test_session.id
            )

        if runtime_payload is not None:
            if runtime_payload.structure_version != structure_state.structure_version:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Entrance test runtime is stale for the current structure",
                )

            return self.runtime_service.build_runtime_snapshot(runtime_payload)

        logger.info(
            "Rebuilding entrance test runtime from stored responses: session_id={}, structure_version={}",
            entrance_test_session.id,
            structure_state.structure_version,
        )
        assessment_config = self._get_assessment_config(entrance_test_session)
        runtime_snapshot = initialize_runtime(
            structure_state.forest_artifact,
            float(assessment_config["temperature_sharpening"]),
        )
        answer_steps = await self._load_answer_steps(session, entrance_test_session.id)

        for problem_type_id, outcome, difficulty_weight in answer_steps:
            step_result = apply_answer_step(
                graph_artifact=structure_state.graph_artifact,
                forest_artifact=structure_state.forest_artifact,
                runtime=runtime_snapshot,
                answered_problem_type_id=problem_type_id,
                outcome=outcome,
                instance_difficulty_weight=difficulty_weight,
                response_model=self._build_response_model(assessment_config),
                i_dont_know_scalar=float(assessment_config["i_dont_know_scalar"]),
                temperature_sharpening=float(assessment_config["temperature_sharpening"]),
                entropy_stop=float(assessment_config["entropy_stop"]),
                utility_stop=float(assessment_config["utility_stop"]),
                leader_probability_stop=self._coerce_optional_float(
                    assessment_config.get("leader_probability_stop")
                ),
                max_questions=int(assessment_config["max_questions"]),
                available_problem_type_ids=set(structure_state.graph_artifact.node_ids),
                learned_mastery_probability=self._get_projected_learned_mastery_probability(
                    assessment_config
                ),
                unlearned_mastery_probability=self._get_projected_unlearned_mastery_probability(
                    assessment_config
                ),
                projection_confidence_stop=self._get_projection_confidence_stop(
                    assessment_config
                ),
                frontier_confidence_stop=self._get_frontier_confidence_stop(
                    assessment_config
                ),
            )
            runtime_snapshot = step_result.runtime

        await self.runtime_service.save_runtime_snapshot(
            entrance_test_session.id,
            structure_state.structure_version,
            runtime_snapshot,
        )
        return runtime_snapshot


    async def _load_answer_steps(
        self,
        session: "AsyncSession",
        entrance_test_session_id: uuid.UUID,
    ) -> list[tuple[uuid.UUID, Outcome, float]]:
        result = await session.execute(
            select(
                ResponseEvent.problem_type_id,
                ResponseEvent.answer_option_type,
                ResponseEvent.difficulty_weight,
                ResponseEvent.created_at,
                ResponseEvent.id,
            )
            .where(ResponseEvent.entrance_test_session_id == entrance_test_session_id)
            .order_by(ResponseEvent.created_at, ResponseEvent.id)
        )
        rows = result.all()
        answer_steps: list[tuple[uuid.UUID, Outcome, float]] = []

        for problem_type_id, answer_option_type, difficulty_weight, _, _ in rows:
            if problem_type_id is None or answer_option_type is None or difficulty_weight is None:
                raise RuntimeError(
                    f"Response snapshot is incomplete for entrance test session {entrance_test_session_id}"
                )
            answer_steps.append(
                (
                    problem_type_id,
                    self._map_answer_option_type_to_outcome(answer_option_type),
                    float(difficulty_weight),
                )
            )

        logger.info(
            "Loaded entrance test answer replay steps: session_id={}, steps={}",
            entrance_test_session_id,
            len(answer_steps),
        )
        return answer_steps


    @staticmethod
    def _map_answer_option_type_to_outcome(
        answer_option_type: ProblemAnswerOptionType,
    ) -> Outcome:
        if answer_option_type == ProblemAnswerOptionType.RIGHT:
            return Outcome.CORRECT
        if answer_option_type == ProblemAnswerOptionType.WRONG:
            return Outcome.INCORRECT
        return Outcome.I_DONT_KNOW


    @staticmethod
    def _persist_final_result(
        entrance_test_session: EntranceTestSession,
        final_result_response: EntranceTestFinalResultResponse,
    ) -> None:
        entrance_test_session.final_state_index = final_result_response.state_index
        entrance_test_session.final_state_probability = (
            final_result_response.state_probability
        )
        entrance_test_session.learned_problem_type_ids = list(
            final_result_response.learned_problem_type_ids
        )
        entrance_test_session.inner_fringe_problem_type_ids = list(
            final_result_response.inner_fringe_ids
        )
        entrance_test_session.outer_fringe_problem_type_ids = list(
            final_result_response.outer_fringe_ids
        )


    @staticmethod
    def _clear_final_result(entrance_test_session: EntranceTestSession) -> None:
        entrance_test_session.final_state_index = None
        entrance_test_session.final_state_probability = None
        entrance_test_session.learned_problem_type_ids = []
        entrance_test_session.inner_fringe_problem_type_ids = []
        entrance_test_session.outer_fringe_problem_type_ids = []


    def _restore_final_result(
        self,
        entrance_test_session: EntranceTestSession,
        final_result_response: EntranceTestFinalResultResponse | None,
    ) -> None:
        if final_result_response is None:
            self._clear_final_result(entrance_test_session)
            return

        self._persist_final_result(entrance_test_session, final_result_response)


    def _get_assessment_config(
        self,
        entrance_test_session: EntranceTestSession,
    ) -> dict[str, Any]:
        snapshot = self._ensure_business_snapshot(entrance_test_session)
        assessment_config = snapshot.get("entrance_assessment")
        if not isinstance(assessment_config, dict):
            raise RuntimeError("Entrance test session does not have an assessment config snapshot")
        return assessment_config


    def _ensure_business_snapshot(
        self,
        entrance_test_session: EntranceTestSession,
    ) -> dict[str, Any]:
        snapshot = entrance_test_session.business_config_snapshot
        if snapshot is None:
            snapshot = get_app_config().business_snapshot()
            entrance_test_session.business_config_snapshot = snapshot
            logger.warning(
                "Backfilled missing business config snapshot for entrance test session {}",
                entrance_test_session.id,
            )
        if not isinstance(snapshot, dict):
            raise RuntimeError("Business config snapshot must be a JSON object")
        return cast("dict[str, Any]", snapshot)


    @staticmethod
    def _coerce_optional_float(raw_value: Any) -> float | None:
        if raw_value is None:
            return None
        return float(raw_value)


    @staticmethod
    def _get_projected_learned_mastery_probability(
        assessment_config: dict[str, Any],
    ) -> float:
        raw_value = assessment_config.get(
            "projected_learned_mastery_probability",
            0.85,
        )
        return float(raw_value)


    @staticmethod
    def _get_projected_unlearned_mastery_probability(
        assessment_config: dict[str, Any],
    ) -> float:
        raw_value = assessment_config.get(
            "projected_unlearned_mastery_probability",
            0.15,
        )
        return float(raw_value)


    @staticmethod
    def _get_projection_confidence_stop(
        assessment_config: dict[str, Any],
    ) -> float:
        raw_value = assessment_config.get(
            "projection_confidence_stop",
            0.85,
        )
        return float(raw_value)


    @staticmethod
    def _get_frontier_confidence_stop(
        assessment_config: dict[str, Any],
    ) -> float:
        raw_value = assessment_config.get(
            "frontier_confidence_stop",
            0.80,
        )
        return float(raw_value)


    def _build_response_model(
        self,
        assessment_config: dict[str, Any],
    ) -> ResponseModel:
        raw_response_model = assessment_config.get("response_model")
        if not isinstance(raw_response_model, dict):
            response_model = ResponseModel(
                mastered_right=0.93,
                mastered_wrong=0.05,
                mastered_i_dont_know=0.02,
                unmastered_right=0.08,
                unmastered_wrong=0.57,
                unmastered_i_dont_know=0.35,
            )
            logger.warning(
                "Entrance assessment config snapshot does not contain a response model, using defaults: session-scoped fallback={}",
                response_model,
            )
            return response_model

        response_model = ResponseModel(
            mastered_right=self._normalize_probability(
                raw_response_model.get("mastered_right"),
                fallback=0.93,
            ),
            mastered_wrong=self._normalize_probability(
                raw_response_model.get("mastered_wrong"),
                fallback=0.05,
            ),
            mastered_i_dont_know=self._normalize_probability(
                raw_response_model.get("mastered_i_dont_know"),
                fallback=0.02,
            ),
            unmastered_right=self._normalize_probability(
                raw_response_model.get("unmastered_right"),
                fallback=0.08,
            ),
            unmastered_wrong=self._normalize_probability(
                raw_response_model.get("unmastered_wrong"),
                fallback=0.57,
            ),
            unmastered_i_dont_know=self._normalize_probability(
                raw_response_model.get("unmastered_i_dont_know"),
                fallback=0.35,
            ),
        )
        return self._normalize_response_model(response_model)


    @staticmethod
    def _normalize_response_model(response_model: ResponseModel) -> ResponseModel:
        mastered_right, mastered_wrong, mastered_i_dont_know = (
            EntranceTestService._normalize_probability_triplet(
                response_model.mastered_right,
                response_model.mastered_wrong,
                response_model.mastered_i_dont_know,
            )
        )
        unmastered_right, unmastered_wrong, unmastered_i_dont_know = (
            EntranceTestService._normalize_probability_triplet(
                response_model.unmastered_right,
                response_model.unmastered_wrong,
                response_model.unmastered_i_dont_know,
            )
        )
        return ResponseModel(
            mastered_right=mastered_right,
            mastered_wrong=mastered_wrong,
            mastered_i_dont_know=mastered_i_dont_know,
            unmastered_right=unmastered_right,
            unmastered_wrong=unmastered_wrong,
            unmastered_i_dont_know=unmastered_i_dont_know,
        )


    @staticmethod
    def _normalize_probability_triplet(
        first_value: float,
        second_value: float,
        third_value: float,
    ) -> tuple[float, float, float]:
        total = first_value + second_value + third_value
        if total <= 0.0:
            return 1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0

        return (
            first_value / total,
            second_value / total,
            third_value / total,
        )


    @staticmethod
    def _normalize_probability(
        raw_value: Any,
        fallback: float,
    ) -> float:
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            value = fallback

        return min(max(value, 1e-9), 1.0)
