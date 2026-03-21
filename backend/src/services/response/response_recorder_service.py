from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import HTTPException, status

from src.models.alchemy import ResponseEvent
from src.models.pydantic import RecordedResponseState, ResponseCreate
from src.services.problem.loader import load_problem_or_404

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.db.database import DataBase


class ResponseRecorderService:
    def __init__(self, db: "DataBase") -> None:
        self.db = db


    async def record_response(
        self,
        session: "AsyncSession",
        user_id: uuid.UUID,
        data: ResponseCreate,
    ) -> RecordedResponseState:
        problem = await load_problem_or_404(session, data.problem_id)
        answer_option = next(
            (item for item in problem.answer_options if item.id == data.answer_option_id),
            None,
        )
        if answer_option is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Answer option not found for this problem",
            )

        response_event = ResponseEvent(
            user_id=user_id,
            problem_id=problem.id,
            answer_option_id=answer_option.id,
            entrance_test_session_id=data.entrance_test_session_id,
        )
        session.add(response_event)
        await session.flush()

        return RecordedResponseState(
            response_id=response_event.id,
            problem_id=problem.id,
            answer_option_id=answer_option.id,
            answer_option_type=answer_option.type,
        )
