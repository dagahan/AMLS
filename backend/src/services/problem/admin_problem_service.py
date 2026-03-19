from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import HTTPException, status

from src.latex import LatexValidationError, MathJaxValidator
from src.models.alchemy import Problem, ProblemAnswerOption, ProblemSkill
from src.models.pydantic import AdminProblemResponse, ProblemCreate, ProblemUpdate
from src.models.pydantic.problem import (
    ProblemAnswerOptionPayload,
    ProblemSkillPayload,
    ProblemSnapshot,
    validate_answer_options,
)
from src.services.mastery.mastery_cache_manager import MasteryCacheManager
from src.services.problem.loader import (
    ensure_difficulty_exists,
    ensure_skills_exist,
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
        self.mathjax_validator = MathJaxValidator()
        self.mastery_cache_manager = MasteryCacheManager()
        self.problem_query_service = ProblemQueryService(db)


    @transactional
    async def create_problem(self, data: ProblemCreate) -> AdminProblemResponse:
        problem_id = await execute_atomic_step(
            action=lambda: self._create_problem_record(data),
            rollback=lambda created_problem_id: self._delete_problem_record(created_problem_id),
            step_name="create_problem_record",
        )
        await self.mastery_cache_manager.bump_problem_mapping_version()
        return await self.problem_query_service.get_admin_problem(problem_id)


    @transactional
    async def update_problem(self, problem_id: uuid.UUID, data: ProblemUpdate) -> AdminProblemResponse:
        snapshot = await self._get_problem_snapshot(problem_id)
        updated_problem_id = await execute_atomic_step(
            action=lambda: self._update_problem_record(problem_id, data),
            rollback=lambda _: self._restore_problem_snapshot(snapshot),
            step_name="update_problem_record",
        )
        if self._is_mastery_mapping_update(data):
            await self.mastery_cache_manager.bump_problem_mapping_version()
        return await self.problem_query_service.get_admin_problem(updated_problem_id)


    @transactional
    async def delete_problem(self, problem_id: uuid.UUID) -> None:
        snapshot = await self._get_problem_snapshot(problem_id)
        await execute_atomic_step(
            action=lambda: self._delete_problem_record(problem_id),
            rollback=lambda _: self._restore_problem_snapshot(snapshot),
            step_name="delete_problem_record",
        )
        await self.mastery_cache_manager.bump_problem_mapping_version()


    async def _create_problem_record(self, data: ProblemCreate) -> uuid.UUID:
        await self._validate_problem_latex(
            condition=data.condition,
            solution=data.solution,
            answer_options=data.answer_options,
        )

        async with self.db.session_ctx() as session:
            await ensure_subtopic_exists(session, data.subtopic_id)
            await ensure_difficulty_exists(session, data.difficulty_id)
            await ensure_skills_exist(session, [item.skill_id for item in data.skills])

            problem = Problem(
                subtopic_id=data.subtopic_id,
                difficulty_id=data.difficulty_id,
                condition=data.condition,
                solution=data.solution,
                condition_images=data.condition_images,
                solution_images=data.solution_images,
            )
            problem.answer_options = self._build_answer_options(data.answer_options)
            problem.skill_links = self._build_skill_links(data.skills)
            session.add(problem)
            await session.flush()
            return problem.id


    async def _update_problem_record(self, problem_id: uuid.UUID, data: ProblemUpdate) -> uuid.UUID:
        await self._validate_problem_latex(
            condition=data.condition,
            solution=data.solution,
            answer_options=data.answer_options,
        )

        async with self.db.session_ctx() as session:
            problem = await load_problem_or_404(session, problem_id)

            if data.subtopic_id is not None:
                await ensure_subtopic_exists(session, data.subtopic_id)
                problem.subtopic_id = data.subtopic_id

            if data.difficulty_id is not None:
                await ensure_difficulty_exists(session, data.difficulty_id)
                problem.difficulty_id = data.difficulty_id

            if data.skills is not None:
                await ensure_skills_exist(session, [item.skill_id for item in data.skills])

            self._validate_updated_answers(data)
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
            condition_images=list(problem.condition_images),
            solution_images=list(problem.solution_images),
            answer_options=[
                ProblemAnswerOptionPayload(text=item.text, is_correct=item.is_correct)
                for item in problem.answer_options
            ],
            skills=[(item.skill_id, item.weight) for item in problem.skill_links],
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
                    condition_images=snapshot.condition_images,
                    solution_images=snapshot.solution_images,
                )
                session.add(problem)
            else:
                problem.subtopic_id = snapshot.subtopic_id
                problem.difficulty_id = snapshot.difficulty_id
                problem.condition = snapshot.condition
                problem.solution = snapshot.solution
                problem.condition_images = snapshot.condition_images
                problem.solution_images = snapshot.solution_images

            problem.answer_options = self._build_answer_options(snapshot.answer_options)
            problem.skill_links = [
                ProblemSkill(skill_id=skill_id, weight=weight)
                for skill_id, weight in snapshot.skills
            ]
            await session.flush()


    def _apply_problem_update(self, problem: Problem, data: ProblemUpdate) -> None:
        if data.condition is not None:
            problem.condition = data.condition

        if data.solution is not None:
            problem.solution = data.solution

        if data.condition_images is not None:
            problem.condition_images = data.condition_images

        if data.solution_images is not None:
            problem.solution_images = data.solution_images

        if data.answer_options is not None:
            problem.answer_options = self._build_answer_options(data.answer_options)

        if data.skills is not None:
            problem.skill_links = self._build_skill_links(data.skills)


    def _validate_updated_answers(self, data: ProblemUpdate) -> None:
        if data.answer_options is None:
            return

        try:
            validate_answer_options(data.answer_options)
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(error),
            ) from error


    def _build_answer_options(
        self,
        answer_options: list[ProblemAnswerOptionPayload],
    ) -> list[ProblemAnswerOption]:
        return [
            ProblemAnswerOption(text=item.text, is_correct=item.is_correct)
            for item in answer_options
        ]


    def _build_skill_links(
        self,
        skills: list[ProblemSkillPayload],
    ) -> list[ProblemSkill]:
        return [
            ProblemSkill(skill_id=item.skill_id, weight=item.weight)
            for item in skills
        ]


    def _is_mastery_mapping_update(self, data: ProblemUpdate) -> bool:
        return (
            data.subtopic_id is not None
            or data.difficulty_id is not None
            or data.skills is not None
        )


    async def _validate_problem_latex(
        self,
        condition: str | None,
        solution: str | None,
        answer_options: list[ProblemAnswerOptionPayload] | None,
    ) -> None:
        try:
            await self.mathjax_validator.validate_problem_content(
                condition=condition,
                solution=solution,
                answer_options=answer_options,
            )
        except LatexValidationError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(error),
            ) from error
