from __future__ import annotations

from src.models.alchemy import Problem
from src.models.pydantic import (
    AdminProblemResponse,
    ProblemAnswerOptionResponse,
    ProblemResponse,
)
from src.models.pydantic.problem import AdminProblemAnswerOptionResponse
from src.models.pydantic.difficulty import DifficultyResponse
from src.models.pydantic.problem import ProblemSkillResponse
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
        answer_options=_build_admin_answer_option_responses(problem),
        skills=[
            ProblemSkillResponse(skill_id=link.skill_id, weight=link.weight)
            for link in problem.skill_links
        ],
    )


def _build_answer_option_responses(problem: Problem) -> list[ProblemAnswerOptionResponse]:
    return [
        ProblemAnswerOptionResponse(id=option.id, text=option.text)
        for option in problem.answer_options
    ]


def _build_admin_answer_option_responses(problem: Problem) -> list[AdminProblemAnswerOptionResponse]:
    return [
        AdminProblemAnswerOptionResponse(
            id=option.id,
            text=option.text,
            is_correct=option.is_correct,
        )
        for option in problem.answer_options
    ]
