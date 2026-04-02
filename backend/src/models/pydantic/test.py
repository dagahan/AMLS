from __future__ import annotations

from datetime import datetime
from uuid import UUID

from src.models.pydantic.common import AmlsSchema
from src.models.pydantic.graph_assessment import GraphAssessmentResponse
from src.models.pydantic.problem import ProblemResponse
from src.models.pydantic.response import RecordedResponseResponse
from src.storage.db.enums import TestAttemptKind, TestAttemptStatus

__test__ = False


class TestStartRequest(AmlsSchema):
    __test__ = False

    kind: TestAttemptKind


class TestAttemptResponse(AmlsSchema):
    __test__ = False

    id: UUID
    user_id: UUID
    graph_version_id: UUID
    kind: TestAttemptKind
    status: TestAttemptStatus
    current_problem_id: UUID | None
    config_snapshot: dict[str, object]
    metadata_json: dict[str, object]
    started_at: datetime | None
    paused_at: datetime | None
    ended_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TestCurrentProblemResponse(AmlsSchema):
    __test__ = False

    test_attempt: TestAttemptResponse
    problem: ProblemResponse | None


class TestAnswerRequest(AmlsSchema):
    __test__ = False

    problem_id: UUID
    answer_option_id: UUID


class TestAnswerResponse(AmlsSchema):
    __test__ = False

    test_attempt: TestAttemptResponse
    response: RecordedResponseResponse
    next_problem: ProblemResponse | None
    graph_assessment: GraphAssessmentResponse | None
