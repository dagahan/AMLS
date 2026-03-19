from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from src.models.pydantic.common import AmlsSchema


class MasteryBetaValue(AmlsSchema):
    id: UUID
    alpha: Decimal
    beta: Decimal
    mastery: Decimal


class MasteryOverviewCache(AmlsSchema):
    skills: list[MasteryBetaValue]
    subtopics: list[MasteryBetaValue]
    topics: list[MasteryBetaValue]


class MasteryValueResponse(AmlsSchema):
    id: UUID
    mastery: float


class MasteryOverviewResponse(AmlsSchema):
    skills: list[MasteryValueResponse]
    subtopics: list[MasteryValueResponse]
    topics: list[MasteryValueResponse]


class ResponseCreate(AmlsSchema):
    problem_id: UUID
    answer_option_id: UUID


class ResponseCreateResponse(AmlsSchema):
    response_id: UUID
    problem_id: UUID
    answer_option_id: UUID
    correct: bool
    solution: str
    solution_images: list[str]
    skills: list[MasteryValueResponse]
    subtopics: list[MasteryValueResponse]
    topics: list[MasteryValueResponse]


class RecordedResponseState(AmlsSchema):
    response_id: UUID
    problem_id: UUID
    answer_option_id: UUID
    correct: bool
    solution: str
    solution_images: list[str]
    skill_ids: list[UUID]
    subtopic_ids: list[UUID]
    topic_ids: list[UUID]
