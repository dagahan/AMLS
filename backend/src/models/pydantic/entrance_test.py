from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from src.db.enums import EntranceTestStatus
from src.models.pydantic.common import AmlsSchema
from src.models.pydantic.mastery import RecordedResponseState, ResponseCreateResponse
from src.models.pydantic.problem import ProblemResponse

if TYPE_CHECKING:
    from src.models.alchemy.entrance_test import EntranceTestSession


class EntranceTestSessionResponse(AmlsSchema):
    id: UUID
    status: EntranceTestStatus
    problem_ids: list[UUID]
    response_ids: list[UUID]
    total_problems: int
    answered_problems: int
    remaining_problems: int
    current_problem_id: UUID | None
    required: bool
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
    response: ResponseCreateResponse


class StoredEntranceTestAnswerState(AmlsSchema):
    session_id: UUID
    previous_status: EntranceTestStatus
    previous_response_ids: list[UUID]
    previous_completed_at: datetime | None
    session: EntranceTestSessionResponse
    response_state: RecordedResponseState


def build_entrance_test_session_response(
    session: "EntranceTestSession",
) -> EntranceTestSessionResponse:
    answered_problems = len(session.response_ids)
    total_problems = len(session.problem_ids)
    remaining_problems = max(total_problems - answered_problems, 0)
    current_problem_id = None
    if answered_problems < total_problems:
        current_problem_id = session.problem_ids[answered_problems]

    return EntranceTestSessionResponse(
        id=session.id,
        status=session.status,
        problem_ids=session.problem_ids,
        response_ids=session.response_ids,
        total_problems=total_problems,
        answered_problems=answered_problems,
        remaining_problems=remaining_problems,
        current_problem_id=current_problem_id,
        required=session.status in {EntranceTestStatus.PENDING, EntranceTestStatus.ACTIVE},
        started_at=session.started_at,
        completed_at=session.completed_at,
        skipped_at=session.skipped_at,
    )
