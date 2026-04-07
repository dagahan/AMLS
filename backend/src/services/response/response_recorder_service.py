from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from src.core.logging import get_logger
from src.models.alchemy import ResponseEvent
from src.models.pydantic import RecordedResponseState, ResponseCreate

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


logger = get_logger(__name__)


class ResponseRecorderService:
    async def record_response(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        data: ResponseCreate,
    ) -> RecordedResponseState:
        response_event = ResponseEvent(
            user_id=user_id,
            problem_id=data.problem_id,
            answer_option_id=data.answer_option_id,
            test_attempt_id=data.test_attempt_id,
            problem_type_id=data.problem_type_id,
            course_node_id=data.course_node_id,
            answer_option_type=data.answer_option_type,
            difficulty=data.difficulty,
            difficulty_weight=data.difficulty_weight,
            revealed_solution=data.revealed_solution,
        )
        session.add(response_event)
        await session.flush()
        logger.debug(
            "Recorded response event",
            response_id=str(response_event.id),
            user_id=str(user_id),
            problem_id=str(data.problem_id),
            answer_option_id=str(data.answer_option_id) if data.answer_option_id is not None else None,
            test_attempt_id=str(data.test_attempt_id) if data.test_attempt_id is not None else None,
        )

        return RecordedResponseState(
            response_id=response_event.id,
            problem_id=data.problem_id,
            answer_option_id=data.answer_option_id,
            answer_option_type=data.answer_option_type,
            revealed_solution=data.revealed_solution,
        )
