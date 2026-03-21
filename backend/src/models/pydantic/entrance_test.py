from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from src.db.enums import EntranceTestStatus
from src.models.pydantic.common import AmlsSchema
from src.models.pydantic.problem import ProblemResponse
from src.models.pydantic.response import RecordedResponseResponse, RecordedResponseState

if TYPE_CHECKING:
    from src.models.alchemy.entrance_test import EntranceTestSession


class EntranceTestSessionResponse(AmlsSchema):
    id: UUID
    status: EntranceTestStatus
    structure_version: int
    current_problem_id: UUID | None
    started_at: datetime | None
    completed_at: datetime | None
    skipped_at: datetime | None


class EntranceTestCurrentProblemResponse(AmlsSchema):
    session: EntranceTestSessionResponse
    problem: ProblemResponse | None


class EntranceTestAnswerRequest(AmlsSchema):
    problem_id: UUID
    answer_option_id: UUID


class EntranceTestAnswerResponse(AmlsSchema):
    session: EntranceTestSessionResponse
    response: RecordedResponseResponse


class StoredEntranceTestAnswerState(AmlsSchema):
    session_id: UUID
    previous_status: EntranceTestStatus
    previous_current_problem_id: UUID | None
    previous_completed_at: datetime | None
    session: EntranceTestSessionResponse
    response_state: RecordedResponseState


def build_entrance_test_session_response(
    session: "EntranceTestSession",
) -> EntranceTestSessionResponse:
    return EntranceTestSessionResponse(
        id=session.id,
        status=session.status,
        structure_version=session.structure_version,
        current_problem_id=session.current_problem_id,
        started_at=session.started_at,
        completed_at=session.completed_at,
        skipped_at=session.skipped_at,
    )
