from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy import Select, select

from src.core.utils import EnvTools
from src.db.enums import EntranceTestStatus, ProblemAnswerOptionType, UserRole
from src.math_models.entrance_assessment import (
    Outcome,
    apply_answer_step,
    build_final_result,
    initialize_runtime,
    select_next_problem_type,
    should_stop,
)
from src.models.alchemy import (
    Difficulty,
    EntranceTestSession,
    Problem,
    ProblemAnswerOption,
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
from src.transaction_manager.transaction_manager import execute_atomic_step, transactional

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.db.database import DataBase
    from src.math_models.entrance_assessment.types import RuntimeSnapshot
    from src.models.pydantic import EntranceTestStructureState


class EntranceTestService:
    def __init__(self, db: "DataBase") -> None:
        self.db = db
        self.structure_service = EntranceTestStructureService()
        self.runtime_service = EntranceTestRuntimeService()
        self.evaluator_service = EntranceTestEvaluatorService()
        self.problem_picker_service = EntranceTestProblemPickerService()
        self.result_projection_service = EntranceTestResultProjectionService()
        self.response_recorder_service = ResponseRecorderService(db)

        self.i_dont_know_scalar = float(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_I_DONT_KNOW_SCALAR")
        )
        self.ancestor_support_correct = float(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_ANCESTOR_SUPPORT_CORRECT")
        )
        self.ancestor_support_wrong = float(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_ANCESTOR_SUPPORT_WRONG")
        )
        self.descendant_support_correct = float(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_DESCENDANT_SUPPORT_CORRECT")
        )
        self.descendant_support_wrong = float(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_DESCENDANT_SUPPORT_WRONG")
        )
        self.ancestor_decay = float(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_ANCESTOR_DECAY")
        )
        self.descendant_decay = float(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_DESCENDANT_DECAY")
        )
        self.temperature_sharpening = float(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_TEMPERATURE_SHARPENING")
        )
        self.entropy_stop = float(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_ENTROPY_STOP")
        )
        self.utility_stop = float(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_UTILITY_STOP")
        )

        raw_leader_probability_stop = EnvTools.load_env_var(
            "ENTRANCE_ASSESSMENT_LEADER_PROBABILITY_STOP"
        )
        self.leader_probability_stop = (
            float(raw_leader_probability_stop)
            if isinstance(raw_leader_probability_stop, str)
            and raw_leader_probability_stop != ""
            else None
        )
        self.max_questions = int(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_MAX_QUESTIONS")
        )
        self.epsilon = float(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_EPSILON")
        )


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
        )
        session.add(entrance_test_session)
        await session.flush()
        user.entrance_test_session = entrance_test_session
        return entrance_test_session


    async def get_session(self, user_id: uuid.UUID) -> EntranceTestSessionResponse:
        async with self.db.session_ctx() as session:
            entrance_test_session = await self._load_session(session, user_id)
            return build_entrance_test_session_response(entrance_test_session)


    async def get_result(self, user_id: uuid.UUID) -> EntranceTestResultResponse:
        async with self.db.session_ctx() as session:
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
        async with self.db.session_ctx() as session:
            try:
                return await self.structure_service.compile_current_structure(session)
            except ValueError as error:
                logger.warning("Cannot compile entrance test structure: {}", error)
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=str(error),
                ) from error


    async def start_session(self, user_id: uuid.UUID) -> EntranceTestCurrentProblemResponse:
        async with self.db.session_ctx() as session:
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
                structure_state = await self._load_latest_structure_state(session)
                runtime_snapshot = initialize_runtime(
                    structure_state.forest_artifact,
                    self.temperature_sharpening,
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
        async with self.db.session_ctx() as session:
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
        async with self.db.session_ctx() as session:
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
        async with self.db.session_ctx() as session:
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
        async with self.db.session_ctx() as session:
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
                ),
            )
            step_result = apply_answer_step(
                graph_artifact=structure_state.graph_artifact,
                forest_artifact=structure_state.forest_artifact,
                runtime=runtime_snapshot,
                answered_problem_type_id=evaluation_state.problem_type_id,
                outcome=evaluation_state.outcome,
                instance_difficulty_weight=evaluation_state.difficulty_weight,
                i_dont_know_scalar=self.i_dont_know_scalar,
                ancestor_support_correct=self.ancestor_support_correct,
                ancestor_support_wrong=self.ancestor_support_wrong,
                descendant_support_correct=self.descendant_support_correct,
                descendant_support_wrong=self.descendant_support_wrong,
                ancestor_decay=self.ancestor_decay,
                descendant_decay=self.descendant_decay,
                temperature_sharpening=self.temperature_sharpening,
                entropy_stop=self.entropy_stop,
                utility_stop=self.utility_stop,
                leader_probability_stop=self.leader_probability_stop,
                max_questions=self.max_questions,
                epsilon=self.epsilon,
                available_problem_type_ids=set(structure_state.graph_artifact.node_ids),
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
                    "Persisted completed entrance test result after answer: session_id={}, state_index={}, state_probability={}, learned_count={}, inner_fringe_count={}, outer_fringe_count={}",
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
                        "Persisted completed entrance test result after exhausted problems: session_id={}, state_index={}, state_probability={}, learned_count={}, inner_fringe_count={}, outer_fringe_count={}",
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
        async with self.db.session_ctx() as session:
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
            return await self.structure_service.load_latest_compiled_structure(session)
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
        selection = select_next_problem_type(
            graph_artifact=structure_state.graph_artifact,
            runtime=runtime_snapshot,
        )
        stop, stop_reason = should_stop(
            runtime=runtime_snapshot,
            selection=selection,
            entropy_stop=self.entropy_stop,
            utility_stop=self.utility_stop,
            leader_probability_stop=self.leader_probability_stop,
            max_questions=self.max_questions,
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
                "Persisted completed entrance test result at session transition: session_id={}, state_index={}, state_probability={}, learned_count={}, inner_fringe_count={}, outer_fringe_count={}",
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
        runtime_snapshot = initialize_runtime(
            structure_state.forest_artifact,
            self.temperature_sharpening,
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
                i_dont_know_scalar=self.i_dont_know_scalar,
                ancestor_support_correct=self.ancestor_support_correct,
                ancestor_support_wrong=self.ancestor_support_wrong,
                descendant_support_correct=self.descendant_support_correct,
                descendant_support_wrong=self.descendant_support_wrong,
                ancestor_decay=self.ancestor_decay,
                descendant_decay=self.descendant_decay,
                temperature_sharpening=self.temperature_sharpening,
                entropy_stop=self.entropy_stop,
                utility_stop=self.utility_stop,
                leader_probability_stop=self.leader_probability_stop,
                max_questions=self.max_questions,
                epsilon=self.epsilon,
                available_problem_type_ids=set(structure_state.graph_artifact.node_ids),
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
                Problem.problem_type_id,
                ProblemAnswerOption.type,
                Difficulty.coefficient,
                ResponseEvent.created_at,
                ResponseEvent.id,
            )
            .join(Problem, Problem.id == ResponseEvent.problem_id)
            .join(Difficulty, Difficulty.id == Problem.difficulty_id)
            .join(
                ProblemAnswerOption,
                ProblemAnswerOption.id == ResponseEvent.answer_option_id,
            )
            .where(ResponseEvent.entrance_test_session_id == entrance_test_session_id)
            .order_by(ResponseEvent.created_at, ResponseEvent.id)
        )
        rows = result.all()
        answer_steps: list[tuple[uuid.UUID, Outcome, float]] = []

        for problem_type_id, answer_option_type, difficulty_coefficient, _, _ in rows:
            answer_steps.append(
                (
                    problem_type_id,
                    self._map_answer_option_type_to_outcome(answer_option_type),
                    float(difficulty_coefficient),
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
