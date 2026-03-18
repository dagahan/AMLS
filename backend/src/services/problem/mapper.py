from __future__ import annotations

from src.models.alchemy import Problem
from src.models.pydantic import AdminProblemResponse, ProblemAnswerOptionResponse, ProblemResponse
from src.models.pydantic.difficulty import DifficultyResponse
from src.models.pydantic.problem import ProblemSubskillResponse
from src.models.pydantic.topic import SubtopicResponse


def build_problem_response(problem: Problem) -> ProblemResponse:
    return ProblemResponse(
        id=problem.id,
        subtopic=SubtopicResponse.model_validate(problem.subtopic),
        difficulty=DifficultyResponse.model_validate(problem.difficulty),
        condition=problem.condition,
        condition_images=problem.condition_images,
        answer_options=_build_answer_option_responses(problem),
    )


def build_admin_problem_response(problem: Problem) -> AdminProblemResponse:
    return AdminProblemResponse(
        id=problem.id,
        subtopic=SubtopicResponse.model_validate(problem.subtopic),
        difficulty=DifficultyResponse.model_validate(problem.difficulty),
        condition=problem.condition,
        condition_images=problem.condition_images,
        solution=problem.solution,
        solution_images=problem.solution_images,
        answer_options=_build_answer_option_responses(problem),
        right_answer=problem.right_answer,
        subskills=[
            ProblemSubskillResponse(subskill_id=link.subskill_id, weight=link.weight)
            for link in problem.subskill_links
        ],
    )


def _build_answer_option_responses(problem: Problem) -> list[ProblemAnswerOptionResponse]:
    return [
        ProblemAnswerOptionResponse(id=option.id, text=option.text)
        for option in problem.answer_options
    ]
