from __future__ import annotations

import uuid

from src.core.logging import get_logger
from src.models.alchemy import Problem
from src.models.pydantic import AdminProblemResponse, ProblemResponse
from src.services.problem.loader import (
    apply_problem_filters,
    build_problem_statement,
    load_problem_or_404,
)
from src.services.problem.mapper import build_admin_problem_response, build_problem_response
from src.storage.storage_manager import StorageManager
from src.storage.db.enums import DifficultyLevel

logger = get_logger(__name__)


class ProblemQueryService:
    def __init__(self, storage_manager: StorageManager) -> None:
        self.storage_manager = storage_manager


    async def list_problems(
        self,
        topic_id: uuid.UUID | None,
        subtopic_id: uuid.UUID | None,
        difficulty: DifficultyLevel | None,
        problem_type_id: uuid.UUID | None,
        course_node_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> list[ProblemResponse]:
        problems = await self._list_loaded_problems(
            topic_id=topic_id,
            subtopic_id=subtopic_id,
            difficulty=difficulty,
            problem_type_id=problem_type_id,
            course_node_id=course_node_id,
            limit=limit,
            offset=offset,
        )
        logger.debug(
            "Listed problems",
            topic_id=str(topic_id) if topic_id is not None else None,
            subtopic_id=str(subtopic_id) if subtopic_id is not None else None,
            difficulty=difficulty.value if difficulty is not None else None,
            problem_type_id=str(problem_type_id) if problem_type_id is not None else None,
            course_node_id=str(course_node_id) if course_node_id is not None else None,
            limit=limit,
            offset=offset,
            result_count=len(problems),
        )
        return [build_problem_response(problem) for problem in problems]


    async def list_admin_problems(
        self,
        topic_id: uuid.UUID | None,
        subtopic_id: uuid.UUID | None,
        difficulty: DifficultyLevel | None,
        problem_type_id: uuid.UUID | None,
        course_node_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> list[AdminProblemResponse]:
        problems = await self._list_loaded_problems(
            topic_id=topic_id,
            subtopic_id=subtopic_id,
            difficulty=difficulty,
            problem_type_id=problem_type_id,
            course_node_id=course_node_id,
            limit=limit,
            offset=offset,
        )
        logger.debug(
            "Listed admin problems",
            topic_id=str(topic_id) if topic_id is not None else None,
            subtopic_id=str(subtopic_id) if subtopic_id is not None else None,
            difficulty=difficulty.value if difficulty is not None else None,
            problem_type_id=str(problem_type_id) if problem_type_id is not None else None,
            course_node_id=str(course_node_id) if course_node_id is not None else None,
            limit=limit,
            offset=offset,
            result_count=len(problems),
        )
        return [build_admin_problem_response(problem) for problem in problems]


    async def get_problem(self, problem_id: uuid.UUID) -> ProblemResponse:
        problem = await self._get_loaded_problem(problem_id)
        logger.debug("Loaded problem", problem_id=str(problem_id))
        return build_problem_response(problem)


    async def get_admin_problem(self, problem_id: uuid.UUID) -> AdminProblemResponse:
        problem = await self._get_loaded_problem(problem_id)
        logger.debug("Loaded admin problem", problem_id=str(problem_id))
        return build_admin_problem_response(problem)


    async def _list_loaded_problems(
        self,
        topic_id: uuid.UUID | None,
        subtopic_id: uuid.UUID | None,
        difficulty: DifficultyLevel | None,
        problem_type_id: uuid.UUID | None,
        course_node_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> list[Problem]:
        async with self.storage_manager.session_ctx() as session:
            statement = apply_problem_filters(
                statement=build_problem_statement(),
                topic_id=topic_id,
                subtopic_id=subtopic_id,
                difficulty=difficulty,
                problem_type_id=problem_type_id,
                course_node_id=course_node_id,
            ).order_by(Problem.created_at.desc()).limit(limit).offset(offset)
            result = await session.execute(statement)
            return list(result.scalars().unique().all())


    async def _get_loaded_problem(self, problem_id: uuid.UUID) -> Problem:
        async with self.storage_manager.session_ctx() as session:
            return await load_problem_or_404(session, problem_id)
