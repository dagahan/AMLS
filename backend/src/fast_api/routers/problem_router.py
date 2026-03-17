from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.db.models import Difficulty, Problem, ProblemAnswerOption, ProblemSubskill, Subskill, Subtopic
from src.fast_api.dependencies import build_current_admin_dependency
from src.pydantic_schemas import (
    MessageResponse,
    ProblemAnswerOptionResponse,
    ProblemCreate,
    ProblemResponse,
    ProblemSubskillResponse,
    ProblemUpdate,
)
from src.pydantic_schemas.difficulty import DifficultyResponse
from src.pydantic_schemas.skill import SubskillResponse
from src.pydantic_schemas.topic import SubtopicResponse

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.db.database import DataBase
    from src.db.models import User


def get_problem_router(db: "DataBase") -> APIRouter:
    router = APIRouter(prefix="/admin/problems", tags=["admin-problems"])
    current_admin = build_current_admin_dependency(db)


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
        existing_ids = {row for row in result.scalars().all()}
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
                selectinload(Problem.subskill_links).selectinload(ProblemSubskill.subskill),
            )
        )
        problem = result.scalar_one_or_none()
        if problem is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found")
        return problem


    def serialize_problem(problem: Problem) -> ProblemResponse:
        return ProblemResponse(
            id=problem.id,
            subtopic=SubtopicResponse.model_validate(problem.subtopic),
            difficulty=DifficultyResponse.model_validate(problem.difficulty),
            condition_latex=problem.condition_latex,
            solution_latex=problem.solution_latex,
            condition_image_urls=problem.condition_image_urls,
            solution_image_urls=problem.solution_image_urls,
            answer_options=[
                ProblemAnswerOptionResponse.model_validate(option)
                for option in problem.answer_options
            ],
            subskills=[
                ProblemSubskillResponse(
                    subskill=SubskillResponse.model_validate(link.subskill),
                    weight=link.weight,
                )
                for link in problem.subskill_links
            ],
        )


    async def validate_problem_links(
        session: "AsyncSession",
        subtopic_id: uuid.UUID,
        difficulty_id: uuid.UUID,
        subskill_ids: list[uuid.UUID],
    ) -> None:
        await ensure_subtopic_exists(session, subtopic_id)
        await ensure_difficulty_exists(session, difficulty_id)
        await ensure_subskills_exist(session, subskill_ids)


    @router.post("", response_model=ProblemResponse, status_code=201)
    async def create_problem(
        data: ProblemCreate,
        _: "User" = Depends(current_admin),
        session: "AsyncSession" = Depends(db.get_session),
    ) -> ProblemResponse:
        await validate_problem_links(
            session,
            data.subtopic_id,
            data.difficulty_id,
            [item.subskill_id for item in data.subskills],
        )

        problem = Problem(
            subtopic_id=data.subtopic_id,
            difficulty_id=data.difficulty_id,
            condition_latex=data.condition_latex,
            solution_latex=data.solution_latex,
            condition_image_urls=data.condition_image_urls,
            solution_image_urls=data.solution_image_urls,
        )
        problem.answer_options = [
            ProblemAnswerOption(
                position=item.position,
                text_latex=item.text_latex,
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
        await session.commit()
        loaded_problem = await load_problem_or_404(session, problem.id)
        return serialize_problem(loaded_problem)


    @router.get("", response_model=list[ProblemResponse], status_code=200)
    async def list_problems(
        subtopic_id: uuid.UUID | None = Query(default=None),
        difficulty_id: uuid.UUID | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        _: "User" = Depends(current_admin),
        session: "AsyncSession" = Depends(db.get_session),
    ) -> list[ProblemResponse]:
        statement = (
            select(Problem)
            .options(
                selectinload(Problem.subtopic),
                selectinload(Problem.difficulty),
                selectinload(Problem.answer_options),
                selectinload(Problem.subskill_links).selectinload(ProblemSubskill.subskill),
            )
            .order_by(Problem.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if subtopic_id is not None:
            statement = statement.where(Problem.subtopic_id == subtopic_id)
        if difficulty_id is not None:
            statement = statement.where(Problem.difficulty_id == difficulty_id)

        result = await session.execute(statement)
        problems = result.scalars().all()
        return [serialize_problem(problem) for problem in problems]


    @router.get("/{problem_id}", response_model=ProblemResponse, status_code=200)
    async def get_problem(
        problem_id: uuid.UUID,
        _: "User" = Depends(current_admin),
        session: "AsyncSession" = Depends(db.get_session),
    ) -> ProblemResponse:
        problem = await load_problem_or_404(session, problem_id)
        return serialize_problem(problem)


    @router.patch("/{problem_id}", response_model=ProblemResponse, status_code=200)
    async def update_problem(
        problem_id: uuid.UUID,
        data: ProblemUpdate,
        _: "User" = Depends(current_admin),
        session: "AsyncSession" = Depends(db.get_session),
    ) -> ProblemResponse:
        problem = await load_problem_or_404(session, problem_id)

        if data.subtopic_id is not None:
            await ensure_subtopic_exists(session, data.subtopic_id)
            problem.subtopic_id = data.subtopic_id

        if data.difficulty_id is not None:
            await ensure_difficulty_exists(session, data.difficulty_id)
            problem.difficulty_id = data.difficulty_id

        if data.condition_latex is not None:
            problem.condition_latex = data.condition_latex

        if data.solution_latex is not None:
            problem.solution_latex = data.solution_latex

        if data.condition_image_urls is not None:
            problem.condition_image_urls = data.condition_image_urls

        if data.solution_image_urls is not None:
            problem.solution_image_urls = data.solution_image_urls

        if data.answer_options is not None:
            problem.answer_options = [
                ProblemAnswerOption(
                    position=item.position,
                    text_latex=item.text_latex,
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

        await session.commit()
        updated_problem = await load_problem_or_404(session, problem.id)
        return serialize_problem(updated_problem)


    @router.delete("/{problem_id}", response_model=MessageResponse, status_code=200)
    async def delete_problem(
        problem_id: uuid.UUID,
        _: "User" = Depends(current_admin),
        session: "AsyncSession" = Depends(db.get_session),
    ) -> MessageResponse:
        problem = await load_problem_or_404(session, problem_id)
        await session.delete(problem)
        await session.commit()
        return MessageResponse(message="Problem deleted")


    return router
