from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from src.models.alchemy import ResponseEvent
from src.models.pydantic import ProblemSubmitResponse, StudentProgressResponse
from src.models.pydantic.mastery import ResponseCreate
from src.services.mastery.response_service import ResponseService

if TYPE_CHECKING:
    from src.db.database import DataBase


class ProblemSubmissionService:
    def __init__(self, db: "DataBase") -> None:
        self.db = db
        self.response_service = ResponseService(db)


    async def get_student_progress(self, user_id: uuid.UUID) -> StudentProgressResponse:
        async with self.db.session_ctx() as session:
            ranked_responses = (
                select(
                    ResponseEvent.problem_id.label("problem_id"),
                    ResponseEvent.is_correct.label("is_correct"),
                    func.row_number().over(
                        partition_by=(ResponseEvent.user_id, ResponseEvent.problem_id),
                        order_by=(ResponseEvent.created_at.desc(), ResponseEvent.id.desc()),
                    ).label("response_rank"),
                )
                .where(ResponseEvent.user_id == user_id)
                .cte("ranked_responses")
            )
            latest_responses_result = await session.execute(
                select(ranked_responses.c.problem_id, ranked_responses.c.is_correct).where(
                    ranked_responses.c.response_rank == 1
                )
            )

        solved_problem_ids: list[uuid.UUID] = []
        failed_problem_ids: list[uuid.UUID] = []

        for problem_id, is_correct in latest_responses_result.all():
            if is_correct:
                solved_problem_ids.append(problem_id)
            else:
                failed_problem_ids.append(problem_id)

        return StudentProgressResponse(
            solved_problem_ids=sorted(solved_problem_ids, key=str),
            failed_problem_ids=sorted(failed_problem_ids, key=str),
        )

    async def submit_problem(
        self,
        user_id: uuid.UUID,
        problem_id: uuid.UUID,
        answer_option_id: uuid.UUID,
    ) -> ProblemSubmitResponse:
        response = await self.response_service.create_response(
            user_id,
            ResponseCreate(
                problem_id=problem_id,
                answer_option_id=answer_option_id,
            ),
        )
        return ProblemSubmitResponse(
            correct=response.correct,
            solution=response.solution,
            solution_images=response.solution_images,
        )
