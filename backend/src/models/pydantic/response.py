from __future__ import annotations

from uuid import UUID

from src.storage.db.enums import DifficultyLevel, ProblemAnswerOptionType
from src.models.pydantic.common import AmlsSchema


class ResponseCreate(AmlsSchema):
    problem_id: UUID
    answer_option_id: UUID
    test_attempt_id: UUID | None = None
    problem_type_id: UUID | None = None
    course_node_id: UUID | None = None
    answer_option_type: ProblemAnswerOptionType
    difficulty: DifficultyLevel
    difficulty_weight: float
    revealed_solution: bool = False


class RecordedResponseResponse(AmlsSchema):
    response_id: UUID
    problem_id: UUID
    answer_option_id: UUID
    answer_option_type: ProblemAnswerOptionType
    revealed_solution: bool


class RecordedResponseState(RecordedResponseResponse):
    pass
