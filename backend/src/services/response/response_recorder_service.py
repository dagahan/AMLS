from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from src.models.alchemy import ResponseEvent
from src.models.pydantic import RecordedResponseState, ResponseCreate

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


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
            entrance_test_session_id=data.entrance_test_session_id,
            problem_type_id=data.problem_type_id,
            answer_option_type=data.answer_option_type,
            difficulty=data.difficulty,
            difficulty_weight=data.difficulty_weight,
        )
        session.add(response_event)
        await session.flush()

        return RecordedResponseState(
            response_id=response_event.id,
            problem_id=data.problem_id,
            answer_option_id=data.answer_option_id,
            answer_option_type=data.answer_option_type,
        )
