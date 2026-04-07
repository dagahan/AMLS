from __future__ import annotations

from datetime import datetime
from uuid import UUID

from src.models.pydantic.common import AmlsSchema
from src.storage.db.enums import GraphAssessmentReviewStatus, TestAttemptKind


class GraphAssessmentStateResponse(AmlsSchema):
    learned_course_node_ids: list[UUID]
    ready_course_node_ids: list[UUID]
    locked_course_node_ids: list[UUID]
    failed_course_node_ids: list[UUID]
    answered_course_node_ids: list[UUID]


class GraphAssessmentResponse(AmlsSchema):
    id: UUID
    user_id: UUID
    graph_version_id: UUID
    source_test_attempt_id: UUID
    state: GraphAssessmentStateResponse
    state_confidence: float
    is_active: bool
    assessment_kind: TestAttemptKind
    metadata_json: dict[str, object]
    review_status: GraphAssessmentReviewStatus
    review_text: str | None
    review_recommendations: list[str]
    review_model: str | None
    review_error: str | None
    review_generated_at: datetime | None
    measured_at: datetime
    created_at: datetime
    updated_at: datetime


class MasteryHistoryItemResponse(AmlsSchema):
    graph_assessment: GraphAssessmentResponse
    learned_delta: int
    ready_delta: int
    locked_delta: int
    failed_delta: int


class CourseMasteryHistoryResponse(AmlsSchema):
    items: list[MasteryHistoryItemResponse]
