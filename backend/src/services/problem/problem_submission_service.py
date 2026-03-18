from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import delete, select

from src.models.alchemy import Problem, UserFailedProblem, UserSolvedProblem
from src.models.pydantic import ProblemSubmitResponse, StudentProgressResponse
from src.models.pydantic.problem import SubmissionSnapshot
from src.services.problem.loader import load_problem_or_404
from src.transaction_manager.transaction_manager import execute_atomic_step, transactional

if TYPE_CHECKING:
    from src.db.database import DataBase


class ProblemSubmissionService:
    def __init__(self, db: "DataBase") -> None:
        self.db = db


    async def get_student_progress(self, user_id: uuid.UUID) -> StudentProgressResponse:
        async with self.db.session_ctx() as session:
            solved_result = await session.execute(
                select(UserSolvedProblem.problem_id).where(UserSolvedProblem.user_id == user_id)
            )
            failed_result = await session.execute(
                select(UserFailedProblem.problem_id).where(UserFailedProblem.user_id == user_id)
            )

        return StudentProgressResponse(
            solved_problem_ids=list(solved_result.scalars().all()),
            failed_problem_ids=list(failed_result.scalars().all()),
        )


    @transactional
    async def submit_problem(
        self,
        user_id: uuid.UUID,
        problem_id: uuid.UUID,
        answer_option_id: uuid.UUID,
    ) -> ProblemSubmitResponse:
        snapshot = await self._get_submission_snapshot(user_id, problem_id)
        return await execute_atomic_step(
            action=lambda: self._store_submission(user_id, problem_id, answer_option_id),
            rollback=lambda _: self._restore_submission_snapshot(snapshot),
            step_name="submit_problem",
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


    async def _restore_submission_snapshot(self, snapshot: SubmissionSnapshot) -> None:
        async with self.db.session_ctx() as session:
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


    async def _store_submission(
        self,
        user_id: uuid.UUID,
        problem_id: uuid.UUID,
        answer_option_id: uuid.UUID,
    ) -> ProblemSubmitResponse:
        async with self.db.session_ctx() as session:
            problem = await load_problem_or_404(session, problem_id)
            self._ensure_problem_contains_answer(problem, answer_option_id)
            is_correct = any(
                answer_option.id == answer_option_id and answer_option.text == problem.right_answer
                for answer_option in problem.answer_options
            )

            await session.execute(
                delete(UserSolvedProblem).where(
                    UserSolvedProblem.user_id == user_id,
                    UserSolvedProblem.problem_id == problem_id,
                )
            )
            await session.execute(
                delete(UserFailedProblem).where(
                    UserFailedProblem.user_id == user_id,
                    UserFailedProblem.problem_id == problem_id,
                )
            )

            if is_correct:
                session.add(UserSolvedProblem(user_id=user_id, problem_id=problem_id))
            else:
                session.add(UserFailedProblem(user_id=user_id, problem_id=problem_id))

        return ProblemSubmitResponse(
            correct=is_correct,
            solution=problem.solution,
            solution_images=problem.solution_images,
        )


    def _ensure_problem_contains_answer(self, problem: Problem, answer_option_id: uuid.UUID) -> None:
        if any(answer_option.id == answer_option_id for answer_option in problem.answer_options):
            return

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Answer option not found for this problem",
        )
