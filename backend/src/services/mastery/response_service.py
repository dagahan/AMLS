from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import delete, select

from src.models.alchemy import (
    ResponseEvent,
    SkillSubskill,
    Subskill,
    Subtopic,
    TopicSubtopic,
    UserFailedProblem,
    UserSolvedProblem,
)
from src.models.pydantic.mastery import (
    MasteryValueResponse,
    RecordedResponseState,
    ResponseCreate,
    ResponseCreateResponse,
)
from src.models.pydantic.problem import SubmissionSnapshot
from src.services.mastery.mastery_cache_manager import MasteryCacheManager
from src.services.mastery.mastery_service import MasteryService
from src.services.problem.loader import load_problem_or_404
from src.transaction_manager.transaction_manager import execute_atomic_step, transactional

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.db.database import DataBase


class ResponseService:
    def __init__(self, db: "DataBase") -> None:
        self.db = db
        self.cache_manager = MasteryCacheManager()
        self.mastery_service = MasteryService(db)


    @transactional
    async def create_response(self, user_id: uuid.UUID, data: ResponseCreate) -> ResponseCreateResponse:
        snapshot = await self._get_submission_snapshot(user_id, data.problem_id)
        response_state = await execute_atomic_step(
            action=lambda: self._store_response(user_id, data),
            rollback=lambda stored_state: self._rollback_response(stored_state, snapshot),
            step_name="store_response",
        )

        await self.cache_manager.bump_user_answers_version(str(user_id))
        overview = await self.mastery_service.get_mastery_overview(user_id)

        return ResponseCreateResponse(
            response_id=response_state.response_id,
            problem_id=response_state.problem_id,
            answer_option_id=response_state.answer_option_id,
            correct=response_state.correct,
            solution=response_state.solution,
            solution_images=response_state.solution_images,
            subskills=self._filter_mastery_values(overview.subskills, response_state.subskill_ids),
            skills=self._filter_mastery_values(overview.skills, response_state.skill_ids),
            subtopics=self._filter_mastery_values(overview.subtopics, response_state.subtopic_ids),
            topics=self._filter_mastery_values(overview.topics, response_state.topic_ids),
        )


    async def _store_response(self, user_id: uuid.UUID, data: ResponseCreate) -> RecordedResponseState:
        async with self.db.session_ctx() as session:
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

            is_correct = answer_option.text == problem.right_answer
            response_event = ResponseEvent(
                user_id=user_id,
                problem_id=problem.id,
                answer_option_id=answer_option.id,
                is_correct=is_correct,
            )
            session.add(response_event)

            await session.execute(
                delete(UserSolvedProblem).where(
                    UserSolvedProblem.user_id == user_id,
                    UserSolvedProblem.problem_id == problem.id,
                )
            )
            await session.execute(
                delete(UserFailedProblem).where(
                    UserFailedProblem.user_id == user_id,
                    UserFailedProblem.problem_id == problem.id,
                )
            )

            if is_correct:
                session.add(UserSolvedProblem(user_id=user_id, problem_id=problem.id))
            else:
                session.add(UserFailedProblem(user_id=user_id, problem_id=problem.id))

            await session.flush()

            subskill_ids = [item.subskill_id for item in problem.subskill_links]
            skill_ids = await self._load_affected_skill_ids(session, subskill_ids)
            subtopic_ids = [problem.subtopic_id]
            topic_ids = await self._load_affected_topic_ids(session, problem.subtopic_id)

            return RecordedResponseState(
                response_id=response_event.id,
                problem_id=problem.id,
                answer_option_id=answer_option.id,
                correct=is_correct,
                solution=problem.solution,
                solution_images=problem.solution_images,
                subskill_ids=subskill_ids,
                skill_ids=skill_ids,
                subtopic_ids=subtopic_ids,
                topic_ids=topic_ids,
            )


    async def _rollback_response(
        self,
        stored_state: RecordedResponseState,
        snapshot: SubmissionSnapshot,
    ) -> None:
        async with self.db.session_ctx() as session:
            response_event = await session.get(ResponseEvent, stored_state.response_id)
            if response_event is not None:
                await session.delete(response_event)

            await session.execute(
                delete(UserSolvedProblem).where(
                    UserSolvedProblem.user_id == snapshot.user_id,
                    UserSolvedProblem.problem_id == snapshot.problem_id,
                )
            )
            await session.execute(
                delete(UserFailedProblem).where(
                    UserFailedProblem.user_id == snapshot.user_id,
                    UserFailedProblem.problem_id == snapshot.problem_id,
                )
            )

            if snapshot.solved_exists:
                session.add(
                    UserSolvedProblem(user_id=snapshot.user_id, problem_id=snapshot.problem_id)
                )

            if snapshot.failed_exists:
                session.add(
                    UserFailedProblem(user_id=snapshot.user_id, problem_id=snapshot.problem_id)
                )


    async def _get_submission_snapshot(
        self,
        user_id: uuid.UUID,
        problem_id: uuid.UUID,
    ) -> SubmissionSnapshot:
        async with self.db.session_ctx() as session:
            solved_result = await session.execute(
                select(UserSolvedProblem).where(
                    UserSolvedProblem.user_id == user_id,
                    UserSolvedProblem.problem_id == problem_id,
                )
            )
            failed_result = await session.execute(
                select(UserFailedProblem).where(
                    UserFailedProblem.user_id == user_id,
                    UserFailedProblem.problem_id == problem_id,
                )
            )

        return SubmissionSnapshot(
            user_id=user_id,
            problem_id=problem_id,
            solved_exists=solved_result.scalar_one_or_none() is not None,
            failed_exists=failed_result.scalar_one_or_none() is not None,
        )


    async def _load_affected_skill_ids(
        self,
        session: "AsyncSession",
        subskill_ids: list[uuid.UUID],
    ) -> list[uuid.UUID]:
        if not subskill_ids:
            return []

        explicit_result = await session.execute(
            select(SkillSubskill.skill_id).where(SkillSubskill.subskill_id.in_(subskill_ids))
        )
        fallback_result = await session.execute(
            select(Subskill.skill_id).where(Subskill.id.in_(subskill_ids))
        )
        skill_ids = set(explicit_result.scalars().all())
        skill_ids.update(fallback_result.scalars().all())
        return sorted(skill_ids, key=str)


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
