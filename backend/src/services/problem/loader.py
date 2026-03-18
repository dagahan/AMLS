from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.orm import selectinload

from src.models.alchemy import Difficulty, Problem, ProblemSubskill, Subskill, Subtopic

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def build_problem_statement() -> Select[tuple[Problem]]:
    return select(Problem).options(
        selectinload(Problem.subtopic),
        selectinload(Problem.difficulty),
        selectinload(Problem.answer_options),
        selectinload(Problem.subskill_links),
    )


def apply_problem_filters(
    statement: Select[tuple[Problem]],
    topic_id: uuid.UUID | None,
    subtopic_id: uuid.UUID | None,
    difficulty_id: uuid.UUID | None,
    subskill_id: uuid.UUID | None,
) -> Select[tuple[Problem]]:
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


async def ensure_difficulty_exists(session: "AsyncSession", difficulty_id: uuid.UUID) -> None:
    result = await session.execute(select(Difficulty.id).where(Difficulty.id == difficulty_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Difficulty not found")


async def ensure_subskills_exist(session: "AsyncSession", subskill_ids: list[uuid.UUID]) -> None:
    result = await session.execute(select(Subskill.id).where(Subskill.id.in_(subskill_ids)))
    existing_ids = set(result.scalars().all())
    missing_ids = [subskill_id for subskill_id in subskill_ids if subskill_id not in existing_ids]
    if missing_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subskills not found: {', '.join(str(item) for item in missing_ids)}",
        )
