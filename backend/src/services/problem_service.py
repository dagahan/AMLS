from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, cast

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from src.db.models import (
    Difficulty,
    Problem,
    ProblemAnswerOption,
    ProblemSubskill,
    Subskill,
    Subtopic,
    UserFailedProblem,
    UserSolvedProblem,
)
from src.pydantic_schemas import (
    AdminProblemResponse,
    ProblemAnswerOptionResponse,
    ProblemCreate,
    ProblemSnapshot,
    ProblemResponse,
    ProblemSubmitResponse,
    ProblemUpdate,
    StudentProgressResponse,
    SubmissionSnapshot,
)
from src.pydantic_schemas.difficulty import DifficultyResponse
from src.pydantic_schemas.problem import ProblemSubskillResponse
from src.pydantic_schemas.topic import SubtopicResponse
from src.transaction_manager.transaction_manager import execute_atomic_step, transactional

if TYPE_CHECKING:
    from src.db.database import DataBase


class ProblemService:
    def __init__(self, db: "DataBase") -> None:
        self.db = db


    async def list_problems(
        self,
        topic_id: uuid.UUID | None,
        subtopic_id: uuid.UUID | None,
        difficulty_id: uuid.UUID | None,
        subskill_id: uuid.UUID | None,
        limit: int,
        offset: int,
        include_admin_data: bool,
    ) -> list[ProblemResponse] | list[AdminProblemResponse]:
        async with self.db.session_ctx() as session:
            statement = (
                select(Problem)
                .options(
                    selectinload(Problem.subtopic),
                    selectinload(Problem.difficulty),
                    selectinload(Problem.answer_options),
                    selectinload(Problem.subskill_links),
                )
                .order_by(Problem.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            statement = self._apply_problem_filters(
                statement=statement,
                topic_id=topic_id,
                subtopic_id=subtopic_id,
                difficulty_id=difficulty_id,
                subskill_id=subskill_id,
            )
            result = await session.execute(statement)
            problems = list(result.scalars().unique().all())

        if include_admin_data:
            return [self._build_admin_problem_response(problem) for problem in problems]

        return [self._build_problem_response(problem) for problem in problems]


    async def get_problem(
        self,
        problem_id: uuid.UUID,
        include_admin_data: bool,
    ) -> ProblemResponse | AdminProblemResponse:
        async with self.db.session_ctx() as session:
            problem = await self._load_problem_or_404(session, problem_id)

        if include_admin_data:
            return self._build_admin_problem_response(problem)

        return self._build_problem_response(problem)


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
    async def create_problem(self, data: ProblemCreate) -> AdminProblemResponse:
        problem_id = await execute_atomic_step(
            action=lambda: self._create_problem_record(data),
            rollback=lambda created_problem_id: self._delete_problem_record(created_problem_id),
            step_name="create_problem_record",
        )
        response = await self.get_problem(problem_id, include_admin_data=True)
        return self._require_admin_response(response)


    @transactional
    async def update_problem(self, problem_id: uuid.UUID, data: ProblemUpdate) -> AdminProblemResponse:
        snapshot = await self._get_problem_snapshot(problem_id)
        updated_problem_id = await execute_atomic_step(
            action=lambda: self._update_problem_record(problem_id, data),
            rollback=lambda _: self._restore_problem_snapshot(snapshot),
            step_name="update_problem_record",
        )
        response = await self.get_problem(updated_problem_id, include_admin_data=True)
        return self._require_admin_response(response)


    @transactional
    async def delete_problem(self, problem_id: uuid.UUID) -> None:
        snapshot = await self._get_problem_snapshot(problem_id)
        await execute_atomic_step(
            action=lambda: self._delete_problem_record(problem_id),
            rollback=lambda _: self._restore_problem_snapshot(snapshot),
            step_name="delete_problem_record",
        )


    @transactional
    async def submit_problem(
        self,
        user_id: uuid.UUID,
        problem_id: uuid.UUID,
        answer_option_id: uuid.UUID,
    ) -> ProblemSubmitResponse:
        previous_state = await self._get_submission_snapshot(user_id, problem_id)
        return await execute_atomic_step(
            action=lambda: self._store_submission(user_id, problem_id, answer_option_id),
            rollback=lambda _: self._restore_submission_snapshot(previous_state),
            step_name="submit_problem",
        )


    async def _create_problem_record(self, data: ProblemCreate) -> uuid.UUID:
        async with self.db.session_ctx() as session:
            await self._ensure_subtopic_exists(session, data.subtopic_id)
            await self._ensure_difficulty_exists(session, data.difficulty_id)
            await self._ensure_subskills_exist(session, [item.subskill_id for item in data.subskills])

            problem = Problem(
                subtopic_id=data.subtopic_id,
                difficulty_id=data.difficulty_id,
                condition=data.condition,
                solution=data.solution,
                right_answer=data.right_answer,
                condition_images=data.condition_images,
                solution_images=data.solution_images,
            )
            problem.answer_options = [ProblemAnswerOption(text=item) for item in data.answer_options]
            problem.subskill_links = [
                ProblemSubskill(subskill_id=item.subskill_id, weight=item.weight)
                for item in data.subskills
            ]
            session.add(problem)
            await session.flush()
            return problem.id


    async def _update_problem_record(self, problem_id: uuid.UUID, data: ProblemUpdate) -> uuid.UUID:
        async with self.db.session_ctx() as session:
            problem = await self._load_problem_or_404(session, problem_id)

            if data.subtopic_id is not None:
                await self._ensure_subtopic_exists(session, data.subtopic_id)
                problem.subtopic_id = data.subtopic_id

            if data.difficulty_id is not None:
                await self._ensure_difficulty_exists(session, data.difficulty_id)
                problem.difficulty_id = data.difficulty_id

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
                problem.answer_options = [ProblemAnswerOption(text=item) for item in data.answer_options]

            if data.subskills is not None:
                await self._ensure_subskills_exist(session, [item.subskill_id for item in data.subskills])
                problem.subskill_links = [
                    ProblemSubskill(subskill_id=item.subskill_id, weight=item.weight)
                    for item in data.subskills
                ]

            await session.flush()
            return problem.id


    async def _delete_problem_record(self, problem_id: uuid.UUID) -> None:
        async with self.db.session_ctx() as session:
            problem = await self._load_problem_or_404(session, problem_id)
            await session.delete(problem)


    async def _get_problem_snapshot(self, problem_id: uuid.UUID) -> ProblemSnapshot:
        async with self.db.session_ctx() as session:
            problem = await self._load_problem_or_404(session, problem_id)

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
            existing_problem = await session.get(Problem, snapshot.id)
            if existing_problem is None:
                existing_problem = Problem(
                    id=snapshot.id,
                    subtopic_id=snapshot.subtopic_id,
                    difficulty_id=snapshot.difficulty_id,
                    condition=snapshot.condition,
                    solution=snapshot.solution,
                    right_answer=snapshot.right_answer,
                    condition_images=snapshot.condition_images,
                    solution_images=snapshot.solution_images,
                )
                session.add(existing_problem)
            else:
                existing_problem.subtopic_id = snapshot.subtopic_id
                existing_problem.difficulty_id = snapshot.difficulty_id
                existing_problem.condition = snapshot.condition
                existing_problem.solution = snapshot.solution
                existing_problem.right_answer = snapshot.right_answer
                existing_problem.condition_images = snapshot.condition_images
                existing_problem.solution_images = snapshot.solution_images

            existing_problem.answer_options = [
                ProblemAnswerOption(text=item)
                for item in snapshot.answer_options
            ]
            existing_problem.subskill_links = [
                ProblemSubskill(subskill_id=subskill_id, weight=weight)
                for subskill_id, weight in snapshot.subskills
            ]
            await session.flush()


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
            problem = await self._load_problem_or_404(session, problem_id)
            answer_option = next(
                (item for item in problem.answer_options if item.id == answer_option_id),
                None,
            )
            if answer_option is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Answer option not found for this problem",
                )

            is_correct = answer_option.text == problem.right_answer

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


    async def _ensure_subtopic_exists(self, session: Any, subtopic_id: uuid.UUID) -> None:
        result = await session.execute(select(Subtopic.id).where(Subtopic.id == subtopic_id))
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subtopic not found")


    async def _ensure_difficulty_exists(self, session: Any, difficulty_id: uuid.UUID) -> None:
        result = await session.execute(select(Difficulty.id).where(Difficulty.id == difficulty_id))
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Difficulty not found")


    async def _ensure_subskills_exist(self, session: Any, subskill_ids: list[uuid.UUID]) -> None:
        result = await session.execute(select(Subskill.id).where(Subskill.id.in_(subskill_ids)))
        existing_ids = set(result.scalars().all())
        missing_ids = [subskill_id for subskill_id in subskill_ids if subskill_id not in existing_ids]
        if missing_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Subskills not found: {', '.join(str(item) for item in missing_ids)}",
            )


    async def _load_problem_or_404(self, session: Any, problem_id: uuid.UUID) -> Problem:
        result = await session.execute(
            select(Problem)
            .where(Problem.id == problem_id)
            .options(
                selectinload(Problem.subtopic),
                selectinload(Problem.difficulty),
                selectinload(Problem.answer_options),
                selectinload(Problem.subskill_links),
            )
        )
        problem = result.scalar_one_or_none()
        if problem is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found")
        return cast("Problem", problem)


    def _apply_problem_filters(
        self,
        statement: Any,
        topic_id: uuid.UUID | None,
        subtopic_id: uuid.UUID | None,
        difficulty_id: uuid.UUID | None,
        subskill_id: uuid.UUID | None,
    ) -> Any:
        if topic_id is not None:
            statement = statement.join(Subtopic, Problem.subtopic_id == Subtopic.id).where(
                Subtopic.topic_id == topic_id
            )

        if subtopic_id is not None:
            statement = statement.where(Problem.subtopic_id == subtopic_id)

        if difficulty_id is not None:
            statement = statement.where(Problem.difficulty_id == difficulty_id)

        if subskill_id is not None:
            statement = statement.join(
                ProblemSubskill,
                ProblemSubskill.problem_id == Problem.id,
            ).where(ProblemSubskill.subskill_id == subskill_id)

        return statement


    def _build_problem_response(self, problem: Problem) -> ProblemResponse:
        return ProblemResponse(
            id=problem.id,
            subtopic=SubtopicResponse.model_validate(problem.subtopic),
            difficulty=DifficultyResponse.model_validate(problem.difficulty),
            condition=problem.condition,
            condition_images=problem.condition_images,
            answer_options=[
                ProblemAnswerOptionResponse(id=option.id, text=option.text)
                for option in problem.answer_options
            ],
        )


    def _build_admin_problem_response(self, problem: Problem) -> AdminProblemResponse:
        return AdminProblemResponse(
            id=problem.id,
            subtopic=SubtopicResponse.model_validate(problem.subtopic),
            difficulty=DifficultyResponse.model_validate(problem.difficulty),
            condition=problem.condition,
            condition_images=problem.condition_images,
            solution=problem.solution,
            solution_images=problem.solution_images,
            answer_options=[
                ProblemAnswerOptionResponse(id=option.id, text=option.text)
                for option in problem.answer_options
            ],
            right_answer=problem.right_answer,
            subskills=[
                ProblemSubskillResponse(subskill_id=link.subskill_id, weight=link.weight)
                for link in problem.subskill_links
            ],
        )


    def _require_admin_response(
        self,
        response: ProblemResponse | AdminProblemResponse,
    ) -> AdminProblemResponse:
        if not isinstance(response, AdminProblemResponse):
            raise RuntimeError("Expected admin problem response")
        return response
