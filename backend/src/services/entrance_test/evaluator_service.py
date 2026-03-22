from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from loguru import logger

from src.config import get_app_config
from src.storage.db.enums import ProblemAnswerOptionType
from src.math_models.entrance_assessment import Outcome
from src.models.pydantic import EntranceTestEvaluationState
from src.services.problem.loader import load_problem_or_404

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class EntranceTestEvaluatorService:
    async def evaluate_answer(
        self,
        session: "AsyncSession",
        problem_id: uuid.UUID,
        answer_option_id: uuid.UUID,
    ) -> EntranceTestEvaluationState:
        problem = await load_problem_or_404(session, problem_id)
        answer_option = next(
            (item for item in problem.answer_options if item.id == answer_option_id),
            None,
        )
        if answer_option is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Answer option not found for this problem",
            )

        difficulty_config = get_app_config().get_difficulty(problem.difficulty.value)
        outcome = self._map_answer_option_type_to_outcome(answer_option.type)
        difficulty_weight = float(difficulty_config["coefficient"])

        logger.info(
            "Evaluated entrance test answer: problem_id={}, problem_type_id={}, answer_option_id={}, answer_option_type={}, outcome={}, difficulty_weight={}",
            problem.id,
            problem.problem_type_id,
            answer_option.id,
            answer_option.type,
            outcome,
            difficulty_weight,
        )
        return EntranceTestEvaluationState(
            problem_id=problem.id,
            problem_type_id=problem.problem_type_id,
            answer_option_id=answer_option.id,
            answer_option_type=answer_option.type,
            difficulty=problem.difficulty,
            outcome=outcome,
            difficulty_weight=difficulty_weight,
        )


    @staticmethod
    def _map_answer_option_type_to_outcome(
        answer_option_type: ProblemAnswerOptionType,
    ) -> Outcome:
        if answer_option_type == ProblemAnswerOptionType.RIGHT:
            return Outcome.CORRECT
        if answer_option_type == ProblemAnswerOptionType.WRONG:
            return Outcome.INCORRECT
        return Outcome.I_DONT_KNOW
