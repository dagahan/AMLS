from __future__ import annotations

from src.models.alchemy import Problem
from src.models.pydantic import (
    AdminProblemResponse,
    ProblemAnswerOptionResponse,
    ProblemResponse,
)
from src.models.pydantic.problem import AdminProblemAnswerOptionResponse
from src.models.pydantic.problem_type import ProblemTypeResponse
from src.models.pydantic.topic import SubtopicResponse
from src.services.catalog.difficulty_service import build_difficulty_response


def build_problem_response(problem: Problem) -> ProblemResponse:
    return ProblemResponse(
        id=problem.id,
        subtopic=SubtopicResponse.model_validate(problem.subtopic),
        difficulty=build_difficulty_response(problem.difficulty),
        problem_type=_build_problem_type_response(problem),
        condition=problem.condition,
        condition_images=problem.condition_images,
        answer_options=_build_answer_option_responses(problem),
    )


def build_admin_problem_response(problem: Problem) -> AdminProblemResponse:
    return AdminProblemResponse(
        id=problem.id,
        subtopic=SubtopicResponse.model_validate(problem.subtopic),
        difficulty=build_difficulty_response(problem.difficulty),
        problem_type=_build_problem_type_response(problem),
        condition=problem.condition,
        condition_images=problem.condition_images,
        solution=problem.solution,
        solution_images=problem.solution_images,
        answer_options=_build_admin_answer_option_responses(problem),
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
            type=option.type,
        )
        for option in problem.answer_options
    ]


def _build_problem_type_response(problem: Problem) -> ProblemTypeResponse:
    prerequisite_ids = sorted(
        (
            item.prerequisite_problem_type_id
            for item in problem.problem_type.prerequisite_links
        ),
        key=str,
    )
    return ProblemTypeResponse(
        id=problem.problem_type.id,
        name=problem.problem_type.name,
        prerequisite_ids=prerequisite_ids,
    )
