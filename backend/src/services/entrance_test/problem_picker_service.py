from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import select

from src.models.alchemy import Problem, ResponseEvent
from src.services.problem.loader import build_problem_statement

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class EntranceTestProblemPickerService:
    async def pick_problem(
        self,
        session: "AsyncSession",
        entrance_test_session_id: uuid.UUID,
        problem_type_id: uuid.UUID,
    ) -> Problem | None:
        used_problem_ids = await self._load_used_problem_ids(
            session=session,
            entrance_test_session_id=entrance_test_session_id,
        )
        result = await session.execute(
            build_problem_statement()
            .where(Problem.problem_type_id == problem_type_id)
            .order_by(Problem.created_at, Problem.id)
        )
        problems = result.scalars().all()
        if not problems:
            logger.warning(
                "Entrance test problem picker found no problems: session_id={}, problem_type_id={}",
                entrance_test_session_id,
                problem_type_id,
            )
            return None

        unused_problem = next(
            (problem for problem in problems if problem.id not in used_problem_ids),
            None,
        )
        selected_problem = unused_problem or problems[0]

        logger.info(
            "Picked entrance test problem: session_id={}, problem_type_id={}, problem_id={}, reused={}",
            entrance_test_session_id,
            problem_type_id,
            selected_problem.id,
            selected_problem.id in used_problem_ids,
        )
        return selected_problem


    async def _load_used_problem_ids(
        self,
        session: "AsyncSession",
        entrance_test_session_id: uuid.UUID,
    ) -> set[uuid.UUID]:
        result = await session.execute(
            select(ResponseEvent.problem_id).where(
                ResponseEvent.entrance_test_session_id == entrance_test_session_id
            )
        )
        return set(result.scalars().all())
