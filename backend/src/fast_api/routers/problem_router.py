from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
from src.db.transaction_manager import TransactionManager
from src.fast_api.dependencies import (
    build_current_admin_dependency,
    build_current_user_dependency,
    parse_optional_uuid,
)
from src.pydantic_schemas import (
    AdminProblemAnswerOptionResponse,
    AdminProblemResponse,
    MessageResponse,
    ProblemAnswerOptionResponse,
    ProblemCreate,
    ProblemResponse,
    ProblemSubmitRequest,
    ProblemSubmitResponse,
    ProblemSubskillResponse,
    ProblemUpdate,
    StudentProgressResponse,
)
from src.pydantic_schemas.difficulty import DifficultyResponse
from src.pydantic_schemas.topic import SubtopicResponse

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.db.database import DataBase
    from src.db.models import User


def get_problem_router(db: "DataBase") -> APIRouter:
    router = APIRouter()
    current_admin = build_current_admin_dependency(db)
    current_user = build_current_user_dependency(db)
    transaction_manager = TransactionManager(db)


    async def ensure_subtopic_exists(session: "AsyncSession", subtopic_id: uuid.UUID) -> None:
        result = await session.execute(select(Subtopic.id).where(Subtopic.id == subtopic_id))
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subtopic not found")


    async def ensure_difficulty_exists(session: "AsyncSession", difficulty_id: uuid.UUID) -> None:
        result = await session.execute(select(Difficulty.id).where(Difficulty.id == difficulty_id))
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Difficulty not found")


    async def ensure_subskills_exist(
        session: "AsyncSession",
        subskill_ids: list[uuid.UUID],
    ) -> None:
        result = await session.execute(select(Subskill.id).where(Subskill.id.in_(subskill_ids)))
        existing_ids = set(result.scalars().all())
        missing_ids = [subskill_id for subskill_id in subskill_ids if subskill_id not in existing_ids]
        if missing_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Subskills not found: {', '.join(str(item) for item in missing_ids)}",
            )


    async def load_problem_or_404(session: "AsyncSession", problem_id: uuid.UUID) -> Problem:
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
        return problem


    def build_problem_response(problem: Problem) -> ProblemResponse:
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


    def build_admin_problem_response(problem: Problem) -> AdminProblemResponse:
        return AdminProblemResponse(
            id=problem.id,
            subtopic=SubtopicResponse.model_validate(problem.subtopic),
            difficulty=DifficultyResponse.model_validate(problem.difficulty),
            condition=problem.condition,
            condition_images=problem.condition_images,
            solution=problem.solution,
            solution_images=problem.solution_images,
            answer_options=[
                AdminProblemAnswerOptionResponse(
                    id=option.id,
                    text=option.text,
                    is_correct=option.is_correct,
                )
                for option in problem.answer_options
            ],
            subskills=[
                ProblemSubskillResponse(
                    subskill_id=link.subskill_id,
                    weight=link.weight,
                )
                for link in problem.subskill_links
            ],
        )


    def apply_problem_filters(
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


    async def list_filtered_problems(
        topic_id: uuid.UUID | None,
        subtopic_id: uuid.UUID | None,
        difficulty_id: uuid.UUID | None,
        subskill_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> list[Problem]:
        async with transaction_manager.session() as session:
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
            statement = apply_problem_filters(
                statement,
                topic_id=topic_id,
                subtopic_id=subtopic_id,
                difficulty_id=difficulty_id,
                subskill_id=subskill_id,
            )
            result = await session.execute(statement)
            return list(result.scalars().unique().all())


    @router.get("/problems", response_model=list[ProblemResponse], status_code=200)
    async def list_problems(
        topic_id: str | None = Query(default=None),
        subtopic_id: str | None = Query(default=None),
        difficulty_id: str | None = Query(default=None),
        subskill_id: str | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> list[ProblemResponse]:
        problems = await list_filtered_problems(
            topic_id=parse_optional_uuid(topic_id, "topic_id"),
            subtopic_id=parse_optional_uuid(subtopic_id, "subtopic_id"),
            difficulty_id=parse_optional_uuid(difficulty_id, "difficulty_id"),
            subskill_id=parse_optional_uuid(subskill_id, "subskill_id"),
            limit=limit,
            offset=offset,
        )
        return [build_problem_response(problem) for problem in problems]


    @router.get("/problems/{problem_id}", response_model=ProblemResponse, status_code=200)
    async def get_problem(problem_id: uuid.UUID) -> ProblemResponse:
        async with transaction_manager.session() as session:
            problem = await load_problem_or_404(session, problem_id)
            return build_problem_response(problem)


    @router.get("/student/progress", response_model=StudentProgressResponse, status_code=200)
    async def get_student_progress(
        user: "User" = Depends(current_user),
    ) -> StudentProgressResponse:
        async with transaction_manager.session() as session:
            solved_result = await session.execute(
                select(UserSolvedProblem.problem_id).where(UserSolvedProblem.user_id == user.id)
            )
            failed_result = await session.execute(
                select(UserFailedProblem.problem_id).where(UserFailedProblem.user_id == user.id)
            )
            return StudentProgressResponse(
                solved_problem_ids=list(solved_result.scalars().all()),
                failed_problem_ids=list(failed_result.scalars().all()),
            )


    @router.post(
        "/student/problems/{problem_id}/submit",
        response_model=ProblemSubmitResponse,
        status_code=200,
    )
    async def submit_problem(
        problem_id: uuid.UUID,
        data: ProblemSubmitRequest,
        user: "User" = Depends(current_user),
    ) -> ProblemSubmitResponse:
        async with transaction_manager.session() as session:
            problem = await load_problem_or_404(session, problem_id)
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
            await session.execute(
                delete(UserSolvedProblem).where(
                    UserSolvedProblem.user_id == user.id,
                    UserSolvedProblem.problem_id == problem_id,
                )
            )
            await session.execute(
                delete(UserFailedProblem).where(
                    UserFailedProblem.user_id == user.id,
                    UserFailedProblem.problem_id == problem_id,
                )
            )

            if is_correct:
                session.add(UserSolvedProblem(user_id=user.id, problem_id=problem_id))
            else:
                session.add(UserFailedProblem(user_id=user.id, problem_id=problem_id))

            return ProblemSubmitResponse(
                correct=is_correct,
                solution=problem.solution,
                solution_images=problem.solution_images,
            )


    @router.post("/admin/problems", response_model=AdminProblemResponse, status_code=201)
    async def create_problem(
        data: ProblemCreate,
        _: "User" = Depends(current_admin),
    ) -> AdminProblemResponse:
        async with transaction_manager.session() as session:
            await ensure_subtopic_exists(session, data.subtopic_id)
            await ensure_difficulty_exists(session, data.difficulty_id)
            await ensure_subskills_exist(session, [item.subskill_id for item in data.subskills])

            problem = Problem(
                subtopic_id=data.subtopic_id,
                difficulty_id=data.difficulty_id,
                condition=data.condition,
                solution=data.solution,
                condition_images=data.condition_images,
                solution_images=data.solution_images,
            )
            problem.answer_options = [
                ProblemAnswerOption(
                    text=item.text,
                    is_correct=item.is_correct,
                )
                for item in data.answer_options
            ]
            problem.subskill_links = [
                ProblemSubskill(
                    subskill_id=item.subskill_id,
                    weight=item.weight,
                )
                for item in data.subskills
            ]
            session.add(problem)
            await session.flush()
            await session.refresh(problem)
            loaded_problem = await load_problem_or_404(session, problem.id)
            return build_admin_problem_response(loaded_problem)


    @router.get("/admin/problems", response_model=list[AdminProblemResponse], status_code=200)
    async def list_admin_problems(
        topic_id: str | None = Query(default=None),
        subtopic_id: str | None = Query(default=None),
        difficulty_id: str | None = Query(default=None),
        subskill_id: str | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        _: "User" = Depends(current_admin),
    ) -> list[AdminProblemResponse]:
        problems = await list_filtered_problems(
            topic_id=parse_optional_uuid(topic_id, "topic_id"),
            subtopic_id=parse_optional_uuid(subtopic_id, "subtopic_id"),
            difficulty_id=parse_optional_uuid(difficulty_id, "difficulty_id"),
            subskill_id=parse_optional_uuid(subskill_id, "subskill_id"),
            limit=limit,
            offset=offset,
        )
        return [build_admin_problem_response(problem) for problem in problems]


    @router.get("/admin/problems/{problem_id}", response_model=AdminProblemResponse, status_code=200)
    async def get_admin_problem(
        problem_id: uuid.UUID,
        _: "User" = Depends(current_admin),
    ) -> AdminProblemResponse:
        async with transaction_manager.session() as session:
            problem = await load_problem_or_404(session, problem_id)
            return build_admin_problem_response(problem)


    @router.patch("/admin/problems/{problem_id}", response_model=AdminProblemResponse, status_code=200)
    async def update_problem(
        problem_id: uuid.UUID,
        data: ProblemUpdate,
        _: "User" = Depends(current_admin),
    ) -> AdminProblemResponse:
        async with transaction_manager.session() as session:
            problem = await load_problem_or_404(session, problem_id)

            if data.subtopic_id is not None:
                await ensure_subtopic_exists(session, data.subtopic_id)
                problem.subtopic_id = data.subtopic_id

            if data.difficulty_id is not None:
                await ensure_difficulty_exists(session, data.difficulty_id)
                problem.difficulty_id = data.difficulty_id

            if data.condition is not None:
                problem.condition = data.condition

            if data.solution is not None:
                problem.solution = data.solution

            if data.condition_images is not None:
                problem.condition_images = data.condition_images

            if data.solution_images is not None:
                problem.solution_images = data.solution_images

            if data.answer_options is not None:
                problem.answer_options = [
                    ProblemAnswerOption(
                        text=item.text,
                        is_correct=item.is_correct,
                    )
                    for item in data.answer_options
                ]

            if data.subskills is not None:
                await ensure_subskills_exist(session, [item.subskill_id for item in data.subskills])
                problem.subskill_links = [
                    ProblemSubskill(
                        subskill_id=item.subskill_id,
                        weight=item.weight,
                    )
                    for item in data.subskills
                ]

            await session.flush()
            await session.refresh(problem)
            updated_problem = await load_problem_or_404(session, problem.id)
            return build_admin_problem_response(updated_problem)


    @router.delete("/admin/problems/{problem_id}", response_model=MessageResponse, status_code=200)
    async def delete_problem(
        problem_id: uuid.UUID,
        _: "User" = Depends(current_admin),
    ) -> MessageResponse:
        async with transaction_manager.session() as session:
            problem = await load_problem_or_404(session, problem_id)
            await session.delete(problem)
            return MessageResponse(message="Problem deleted")


    return router
