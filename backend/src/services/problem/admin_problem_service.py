from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import HTTPException, status

from src.models.alchemy import Problem, ProblemAnswerOption, ProblemSubskill
from src.models.pydantic import AdminProblemResponse, ProblemCreate, ProblemUpdate
from src.models.pydantic.problem import ProblemSnapshot, ProblemSubskillPayload, validate_answer_options
from src.services.problem.loader import (
    ensure_difficulty_exists,
    ensure_subskills_exist,
    ensure_subtopic_exists,
    load_problem_or_404,
)
from src.services.problem.problem_query_service import ProblemQueryService
from src.transaction_manager.transaction_manager import execute_atomic_step, transactional

if TYPE_CHECKING:
    from src.db.database import DataBase


class AdminProblemService:
    def __init__(self, db: "DataBase") -> None:
        self.db = db
        self.problem_query_service = ProblemQueryService(db)


    @transactional
    async def create_problem(self, data: ProblemCreate) -> AdminProblemResponse:
        problem_id = await execute_atomic_step(
            action=lambda: self._create_problem_record(data),
            rollback=lambda created_problem_id: self._delete_problem_record(created_problem_id),
            step_name="create_problem_record",
        )
        return await self.problem_query_service.get_admin_problem(problem_id)


    @transactional
    async def update_problem(self, problem_id: uuid.UUID, data: ProblemUpdate) -> AdminProblemResponse:
        snapshot = await self._get_problem_snapshot(problem_id)
        updated_problem_id = await execute_atomic_step(
            action=lambda: self._update_problem_record(problem_id, data),
            rollback=lambda _: self._restore_problem_snapshot(snapshot),
            step_name="update_problem_record",
        )
        return await self.problem_query_service.get_admin_problem(updated_problem_id)


    @transactional
    async def delete_problem(self, problem_id: uuid.UUID) -> None:
        snapshot = await self._get_problem_snapshot(problem_id)
        await execute_atomic_step(
            action=lambda: self._delete_problem_record(problem_id),
            rollback=lambda _: self._restore_problem_snapshot(snapshot),
            step_name="delete_problem_record",
        )


    async def _create_problem_record(self, data: ProblemCreate) -> uuid.UUID:
        async with self.db.session_ctx() as session:
            await ensure_subtopic_exists(session, data.subtopic_id)
            await ensure_difficulty_exists(session, data.difficulty_id)
            await ensure_subskills_exist(session, [item.subskill_id for item in data.subskills])

            problem = Problem(
                subtopic_id=data.subtopic_id,
                difficulty_id=data.difficulty_id,
                condition=data.condition,
                solution=data.solution,
                right_answer=data.right_answer,
                condition_images=data.condition_images,
                solution_images=data.solution_images,
            )
            problem.answer_options = self._build_answer_options(data.answer_options)
            problem.subskill_links = self._build_subskill_links(data.subskills)
            session.add(problem)
            await session.flush()
            return problem.id


    async def _update_problem_record(self, problem_id: uuid.UUID, data: ProblemUpdate) -> uuid.UUID:
        async with self.db.session_ctx() as session:
            problem = await load_problem_or_404(session, problem_id)

            if data.subtopic_id is not None:
                await ensure_subtopic_exists(session, data.subtopic_id)
                problem.subtopic_id = data.subtopic_id

            if data.difficulty_id is not None:
                await ensure_difficulty_exists(session, data.difficulty_id)
                problem.difficulty_id = data.difficulty_id

            if data.subskills is not None:
                await ensure_subskills_exist(session, [item.subskill_id for item in data.subskills])

            self._validate_updated_answers(problem, data)
            self._apply_problem_update(problem, data)

            await session.flush()
            return problem.id


    async def _delete_problem_record(self, problem_id: uuid.UUID) -> None:
        async with self.db.session_ctx() as session:
            problem = await load_problem_or_404(session, problem_id)
            await session.delete(problem)


    async def _get_problem_snapshot(self, problem_id: uuid.UUID) -> ProblemSnapshot:
        async with self.db.session_ctx() as session:
            problem = await load_problem_or_404(session, problem_id)

        return ProblemSnapshot(
            id=problem.id,
            subtopic_id=problem.subtopic_id,
            difficulty_id=problem.difficulty_id,
            condition=problem.condition,
            solution=problem.solution,
            right_answer=problem.right_answer,
            condition_images=list(problem.condition_images),
            solution_images=list(problem.solution_images),
            answer_options=[item.text for item in problem.answer_options],
            subskills=[(item.subskill_id, item.weight) for item in problem.subskill_links],
        )


    async def _restore_problem_snapshot(self, snapshot: ProblemSnapshot) -> None:
        async with self.db.session_ctx() as session:
            problem = await session.get(Problem, snapshot.id)
            if problem is None:
                problem = Problem(
                    id=snapshot.id,
                    subtopic_id=snapshot.subtopic_id,
                    difficulty_id=snapshot.difficulty_id,
                    condition=snapshot.condition,
                    solution=snapshot.solution,
                    right_answer=snapshot.right_answer,
                    condition_images=snapshot.condition_images,
                    solution_images=snapshot.solution_images,
                )
                session.add(problem)
            else:
                problem.subtopic_id = snapshot.subtopic_id
                problem.difficulty_id = snapshot.difficulty_id
                problem.condition = snapshot.condition
                problem.solution = snapshot.solution
                problem.right_answer = snapshot.right_answer
                problem.condition_images = snapshot.condition_images
                problem.solution_images = snapshot.solution_images

            problem.answer_options = self._build_answer_options(snapshot.answer_options)
            problem.subskill_links = [
                ProblemSubskill(subskill_id=subskill_id, weight=weight)
                for subskill_id, weight in snapshot.subskills
            ]
            await session.flush()


    def _apply_problem_update(self, problem: Problem, data: ProblemUpdate) -> None:
        if data.condition is not None:
            problem.condition = data.condition

        if data.solution is not None:
            problem.solution = data.solution

        if data.right_answer is not None:
            problem.right_answer = data.right_answer

        if data.condition_images is not None:
            problem.condition_images = data.condition_images

        if data.solution_images is not None:
            problem.solution_images = data.solution_images

        if data.answer_options is not None:
            problem.answer_options = self._build_answer_options(data.answer_options)

        if data.subskills is not None:
            problem.subskill_links = self._build_subskill_links(data.subskills)


    def _validate_updated_answers(self, problem: Problem, data: ProblemUpdate) -> None:
        if data.answer_options is None and data.right_answer is None:
            return

        answer_options = (
            data.answer_options
            if data.answer_options is not None
            else [item.text for item in problem.answer_options]
        )
        right_answer = data.right_answer if data.right_answer is not None else problem.right_answer
        try:
            validate_answer_options(answer_options, right_answer)
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(error),
            ) from error


    def _build_answer_options(self, answer_options: list[str]) -> list[ProblemAnswerOption]:
        return [ProblemAnswerOption(text=item) for item in answer_options]


    def _build_subskill_links(
        self,
        subskills: list[ProblemSubskillPayload],
    ) -> list[ProblemSubskill]:
        return [
            ProblemSubskill(subskill_id=item.subskill_id, weight=item.weight)
            for item in subskills
        ]
