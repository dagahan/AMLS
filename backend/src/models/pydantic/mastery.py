from __future__ import annotations

from uuid import UUID

from src.models.pydantic.common import AmlsSchema


class MasteryValueResponse(AmlsSchema):
    id: UUID
    mastery: float


class MasteryOverviewResponse(AmlsSchema):
    subskills: list[MasteryValueResponse]
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
    subskills: list[MasteryValueResponse]
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
    subskill_ids: list[UUID]
    skill_ids: list[UUID]
    subtopic_ids: list[UUID]
    topic_ids: list[UUID]
