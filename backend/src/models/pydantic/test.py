from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from src.models.pydantic.common import AmlsSchema
from src.models.pydantic.graph_assessment import GraphAssessmentResponse
from src.models.pydantic.problem import ProblemResponse
from src.models.pydantic.response import RecordedResponseResponse
from src.storage.db.enums import ProblemAnswerOptionType, TestAttemptKind, TestAttemptStatus

__test__ = False


class TestStartRequest(AmlsSchema):
    __test__ = False

    kind: TestAttemptKind
    target_course_node_ids: list[UUID] | None = Field(default=None, max_length=128)


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
    total_paused_seconds: int
    elapsed_solve_seconds: int
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


class ProblemSolutionResponse(AmlsSchema):
    problem_id: UUID
    solution: str
    solution_images: list[str]


class TestRevealSolutionResponse(AmlsSchema):
    test_attempt: TestAttemptResponse
    response: RecordedResponseResponse
    revealed_solution: ProblemSolutionResponse
    next_problem: ProblemResponse | None
    graph_assessment: GraphAssessmentResponse | None


class TestReviewResponseItem(AmlsSchema):
    response_id: UUID
    problem: ProblemResponse
    chosen_answer_option_id: UUID | None
    chosen_answer_option_type: ProblemAnswerOptionType
    revealed_solution: bool
    solution: str
    solution_images: list[str]
    created_at: datetime


class TestAttemptReviewResponse(AmlsSchema):
    test_attempt: TestAttemptResponse
    items: list[TestReviewResponseItem]


class CourseTestAttemptHistoryItemResponse(AmlsSchema):
    id: UUID
    graph_version_id: UUID
    kind: TestAttemptKind
    status: TestAttemptStatus
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CourseTestHistoryResponse(AmlsSchema):
    attempts: list[CourseTestAttemptHistoryItemResponse]
