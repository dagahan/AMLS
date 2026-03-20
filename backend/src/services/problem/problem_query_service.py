from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from src.models.alchemy import Problem
from src.models.pydantic import AdminProblemResponse, ProblemResponse
from src.services.problem.loader import (
    apply_problem_filters,
    build_problem_statement,
    load_problem_or_404,
)
from src.services.problem.mapper import build_admin_problem_response, build_problem_response

if TYPE_CHECKING:
    from src.db.database import DataBase


class ProblemQueryService:
    def __init__(self, db: "DataBase") -> None:
        self.db = db


    async def list_problems(
        self,
        topic_id: uuid.UUID | None,
        subtopic_id: uuid.UUID | None,
        difficulty_id: uuid.UUID | None,
        problem_type_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> list[ProblemResponse]:
        problems = await self._list_loaded_problems(
            topic_id=topic_id,
            subtopic_id=subtopic_id,
            difficulty_id=difficulty_id,
            problem_type_id=problem_type_id,
            limit=limit,
            offset=offset,
        )
        return [build_problem_response(problem) for problem in problems]


    async def list_admin_problems(
        self,
        topic_id: uuid.UUID | None,
        subtopic_id: uuid.UUID | None,
        difficulty_id: uuid.UUID | None,
        problem_type_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> list[AdminProblemResponse]:
        problems = await self._list_loaded_problems(
            topic_id=topic_id,
            subtopic_id=subtopic_id,
            difficulty_id=difficulty_id,
            problem_type_id=problem_type_id,
            limit=limit,
            offset=offset,
        )
        return [build_admin_problem_response(problem) for problem in problems]


    async def get_problem(self, problem_id: uuid.UUID) -> ProblemResponse:
        problem = await self._get_loaded_problem(problem_id)
        return build_problem_response(problem)


    async def get_admin_problem(self, problem_id: uuid.UUID) -> AdminProblemResponse:
        problem = await self._get_loaded_problem(problem_id)
        return build_admin_problem_response(problem)


    async def _list_loaded_problems(
        self,
        topic_id: uuid.UUID | None,
        subtopic_id: uuid.UUID | None,
        difficulty_id: uuid.UUID | None,
        problem_type_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> list[Problem]:
        async with self.db.session_ctx() as session:
            statement = apply_problem_filters(
                statement=build_problem_statement(),
                topic_id=topic_id,
                subtopic_id=subtopic_id,
                difficulty_id=difficulty_id,
                problem_type_id=problem_type_id,
            ).order_by(Problem.created_at.desc()).limit(limit).offset(offset)
            result = await session.execute(statement)
            return list(result.scalars().unique().all())


    async def _get_loaded_problem(self, problem_id: uuid.UUID) -> Problem:
        async with self.db.session_ctx() as session:
            return await load_problem_or_404(session, problem_id)
