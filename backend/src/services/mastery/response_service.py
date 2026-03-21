from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import select

from src.models.alchemy import ResponseEvent, Subtopic, TopicSubtopic
from src.models.pydantic.mastery import (
    MasteryValueResponse,
    RecordedResponseState,
    ResponseCreate,
    ResponseCreateResponse,
)
from src.services.mastery.mastery_service import MasteryService
from src.services.problem.loader import load_problem_or_404
from src.transaction_manager.transaction_manager import execute_atomic_step, transactional
from src.valkey.mastery_cache import MasteryCache

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.db.database import DataBase


class ResponseService:
    def __init__(self, db: "DataBase") -> None:
        self.db = db
        self.mastery_cache = MasteryCache()
        self.mastery_service = MasteryService(db)


    @transactional
    async def create_response(self, user_id: uuid.UUID, data: ResponseCreate) -> ResponseCreateResponse:
        response_state = await execute_atomic_step(
            action=lambda: self._store_response(user_id, data),
            rollback=self._rollback_response,
            step_name="store_response",
        )

        return await self.build_response_result(user_id, response_state)


    async def record_response(
        self,
        session: "AsyncSession",
        user_id: uuid.UUID,
        data: ResponseCreate,
    ) -> RecordedResponseState:
        problem = await load_problem_or_404(session, data.problem_id)
        answer_option = next(
            (item for item in problem.answer_options if item.id == data.answer_option_id),
            None,
        )
        if answer_option is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Answer option not found for this problem",
            )

        is_correct = answer_option.is_correct
        response_event = ResponseEvent(
            user_id=user_id,
            problem_id=problem.id,
            answer_option_id=answer_option.id,
            is_correct=is_correct,
        )
        session.add(response_event)
        await session.flush()

        subtopic_ids = [problem.subtopic_id]
        topic_ids = await self._load_affected_topic_ids(session, problem.subtopic_id)

        return RecordedResponseState(
            response_id=response_event.id,
            problem_id=problem.id,
            answer_option_id=answer_option.id,
            correct=is_correct,
            solution=problem.solution,
            solution_images=problem.solution_images,
            subtopic_ids=subtopic_ids,
            topic_ids=topic_ids,
        )


    async def build_response_result(
        self,
        user_id: uuid.UUID,
        response_state: RecordedResponseState,
    ) -> ResponseCreateResponse:
        await self.mastery_cache.bump_user_answers_version(str(user_id))
        overview = await self.mastery_service.get_mastery_overview(user_id)

        return ResponseCreateResponse(
            response_id=response_state.response_id,
            problem_id=response_state.problem_id,
            answer_option_id=response_state.answer_option_id,
            correct=response_state.correct,
            solution=response_state.solution,
            solution_images=response_state.solution_images,
            subtopics=self._filter_mastery_values(overview.subtopics, response_state.subtopic_ids),
            topics=self._filter_mastery_values(overview.topics, response_state.topic_ids),
        )


    async def _store_response(
        self,
        user_id: uuid.UUID,
        data: ResponseCreate,
    ) -> RecordedResponseState:
        async with self.db.session_ctx() as session:
            return await self.record_response(session, user_id, data)


    async def _rollback_response(self, response_state: RecordedResponseState) -> None:
        async with self.db.session_ctx() as session:
            response_event = await session.get(ResponseEvent, response_state.response_id)
            if response_event is not None:
                await session.delete(response_event)


    async def _load_affected_topic_ids(
        self,
        session: "AsyncSession",
        subtopic_id: uuid.UUID,
    ) -> list[uuid.UUID]:
        explicit_result = await session.execute(
            select(TopicSubtopic.topic_id).where(TopicSubtopic.subtopic_id == subtopic_id)
        )
        topic_ids = set(explicit_result.scalars().all())

        if not topic_ids:
            subtopic_result = await session.execute(
                select(Subtopic.topic_id).where(Subtopic.id == subtopic_id)
            )
            topic_id = subtopic_result.scalar_one_or_none()
            if topic_id is not None:
                topic_ids.add(topic_id)
        return sorted(topic_ids, key=str)


    def _filter_mastery_values(
        self,
        mastery_values: list[MasteryValueResponse],
        affected_ids: list[uuid.UUID],
    ) -> list[MasteryValueResponse]:
        affected_id_set = set(affected_ids)
        return [item for item in mastery_values if item.id in affected_id_set]
