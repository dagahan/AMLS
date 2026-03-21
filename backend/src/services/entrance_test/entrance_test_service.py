from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy import Select, select

from src.db.enums import EntranceTestStatus, UserRole
from src.models.alchemy import EntranceTestSession, Problem, ResponseEvent, User
from src.models.pydantic import (
    EntranceTestAnswerRequest,
    EntranceTestAnswerResponse,
    EntranceTestCurrentProblemResponse,
    EntranceTestSessionResponse,
    ResponseCreate,
    StoredEntranceTestAnswerState,
    build_entrance_test_session_response,
)
from src.services.problem.loader import build_problem_statement, load_problem_or_404
from src.services.problem.mapper import build_problem_response
from src.services.entrance_test.assessment_service import EntranceAssessmentService
from src.services.response import ResponseRecorderService
from src.transaction_manager.transaction_manager import execute_atomic_step, transactional

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.db.database import DataBase


class EntranceTestService:
    def __init__(self, db: "DataBase") -> None:
        self.db = db
        self.entrance_assessment_service = EntranceAssessmentService()
        self.response_recorder_service = ResponseRecorderService(db)


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
        )
        session.add(entrance_test_session)
        await session.flush()
        user.entrance_test_session = entrance_test_session
        return entrance_test_session


    async def get_session(self, user_id: uuid.UUID) -> EntranceTestSessionResponse:
        async with self.db.session_ctx() as session:
            entrance_test_session = await self._load_session(session, user_id)
            return build_entrance_test_session_response(entrance_test_session)


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

            if entrance_test_session.status == EntranceTestStatus.PENDING:
                entrance_test_session.status = EntranceTestStatus.ACTIVE
                entrance_test_session.started_at = datetime.now(UTC)

            if entrance_test_session.current_problem_id is None:
                entrance_test_session.current_problem_id = await self.entrance_assessment_service.select_next_problem_id(
                    session,
                    entrance_test_session.id,
                )

            if entrance_test_session.current_problem_id is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Entrance test does not have available problems",
                )

            logger.info(
                "Started entrance test session {} for user {} with current_problem_id={}",
                entrance_test_session.id,
                user_id,
                entrance_test_session.current_problem_id,
            )

            session_response = build_entrance_test_session_response(entrance_test_session)
            current_problem = await self._load_current_problem(session, entrance_test_session)

        return EntranceTestCurrentProblemResponse(
            session=session_response,
            problem=build_problem_response(current_problem),
        )


    async def get_current_problem(self, user_id: uuid.UUID) -> EntranceTestCurrentProblemResponse:
        async with self.db.session_ctx() as session:
            entrance_test_session = await self._load_session(session, user_id)
            session_response = build_entrance_test_session_response(entrance_test_session)
            current_problem = await self._load_optional_current_problem(session, entrance_test_session)

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
                logger.info(
                    "Skipped entrance test session {} for user {}",
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
                logger.info(
                    "Completed entrance test session {} for user {}",
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

            previous_status = entrance_test_session.status
            previous_current_problem_id = entrance_test_session.current_problem_id
            previous_completed_at = entrance_test_session.completed_at

            response_state = await self.response_recorder_service.record_response(
                session,
                user_id,
                ResponseCreate(
                    problem_id=data.problem_id,
                    answer_option_id=data.answer_option_id,
                    entrance_test_session_id=entrance_test_session.id,
                ),
            )
            entrance_test_session.current_problem_id = await self.entrance_assessment_service.select_next_problem_id(
                session,
                entrance_test_session.id,
            )
            if entrance_test_session.current_problem_id is None:
                entrance_test_session.status = EntranceTestStatus.COMPLETED
                entrance_test_session.completed_at = datetime.now(UTC)

            logger.info(
                "Recorded entrance test answer for session {}: problem_id={}, answer_option_id={}, next_problem_id={}, status={}",
                entrance_test_session.id,
                data.problem_id,
                data.answer_option_id,
                entrance_test_session.current_problem_id,
                entrance_test_session.status,
            )

            return StoredEntranceTestAnswerState(
                session_id=entrance_test_session.id,
                previous_status=previous_status,
                previous_current_problem_id=previous_current_problem_id,
                previous_completed_at=previous_completed_at,
                session=build_entrance_test_session_response(entrance_test_session),
                response_state=response_state,
            )


    async def _rollback_session_answer(
        self,
        stored_state: StoredEntranceTestAnswerState,
    ) -> None:
        async with self.db.session_ctx() as session:
            response_event = await session.get(ResponseEvent, stored_state.response_state.response_id)
            if response_event is not None:
                await session.delete(response_event)

            entrance_test_session = await session.get(EntranceTestSession, stored_state.session_id)
            if entrance_test_session is None:
                return

            entrance_test_session.status = stored_state.previous_status
            entrance_test_session.current_problem_id = stored_state.previous_current_problem_id
            entrance_test_session.completed_at = stored_state.previous_completed_at


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

        result = await session.execute(
            build_problem_statement().where(Problem.id == current_problem_id)
        )
        return result.scalar_one_or_none()
