from __future__ import annotations

from uuid import UUID

from src.db.enums import ProblemAnswerOptionType
from src.models.pydantic.common import AmlsSchema


class ResponseCreate(AmlsSchema):
    problem_id: UUID
    answer_option_id: UUID
    entrance_test_session_id: UUID | None = None


class RecordedResponseResponse(AmlsSchema):
    response_id: UUID
    problem_id: UUID
    answer_option_id: UUID
    answer_option_type: ProblemAnswerOptionType


class RecordedResponseState(RecordedResponseResponse):
    pass
