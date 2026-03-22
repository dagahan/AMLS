from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.orm import selectinload

from src.db.enums import DifficultyLevel
from src.models.alchemy import Problem, ProblemType, Subtopic

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def build_problem_statement() -> Select[tuple[Problem]]:
    return select(Problem).options(
        selectinload(Problem.subtopic),
        selectinload(Problem.problem_type).selectinload(ProblemType.prerequisite_links),
        selectinload(Problem.answer_options),
    )


def apply_problem_filters(
    statement: Select[tuple[Problem]],
    topic_id: uuid.UUID | None,
    subtopic_id: uuid.UUID | None,
    difficulty: DifficultyLevel | None,
    problem_type_id: uuid.UUID | None,
) -> Select[tuple[Problem]]:
    if topic_id is not None:
        statement = statement.join(Subtopic, Problem.subtopic_id == Subtopic.id).where(
            Subtopic.topic_id == topic_id
        )

    if subtopic_id is not None:
        statement = statement.where(Problem.subtopic_id == subtopic_id)

    if difficulty is not None:
        statement = statement.where(Problem.difficulty == difficulty)

    if problem_type_id is not None:
        statement = statement.where(Problem.problem_type_id == problem_type_id)

    return statement


async def load_problem_or_404(session: "AsyncSession", problem_id: uuid.UUID) -> Problem:
    result = await session.execute(
        build_problem_statement().where(Problem.id == problem_id)
    )
    problem = result.scalar_one_or_none()
    if problem is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found")
    return problem


async def ensure_subtopic_exists(session: "AsyncSession", subtopic_id: uuid.UUID) -> None:
    result = await session.execute(select(Subtopic.id).where(Subtopic.id == subtopic_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subtopic not found")


def ensure_difficulty_exists(difficulty: DifficultyLevel) -> None:
    if not isinstance(difficulty, DifficultyLevel):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Difficulty not found")


async def ensure_problem_type_exists(
    session: "AsyncSession",
    problem_type_id: uuid.UUID,
) -> None:
    result = await session.execute(select(ProblemType.id).where(ProblemType.id == problem_type_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Problem type not found",
        )
