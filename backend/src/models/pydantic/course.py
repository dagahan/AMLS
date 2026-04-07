from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from src.models.pydantic.common import AmlsSchema
from src.models.pydantic.graph_assessment import GraphAssessmentResponse
from src.storage.db.enums import (
    CourseGraphVersionStatus,
    GraphAssessmentReviewStatus,
    TestAttemptKind,
    TestAttemptStatus,
)


class CourseCreate(AmlsSchema):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1)


class CourseResponse(AmlsSchema):
    id: UUID
    author_id: UUID
    current_graph_version_id: UUID | None
    title: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class CourseEnrollmentResponse(AmlsSchema):
    id: UUID
    user_id: UUID
    course_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CourseNodeCreate(AmlsSchema):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1)
    problem_type_id: UUID | None = None


class CourseNodeUpdate(AmlsSchema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1)
    problem_type_id: UUID | None = None


class CourseNodeResponse(AmlsSchema):
    id: UUID
    course_id: UUID
    problem_type_id: UUID | None
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class CourseGraphVersionCreate(AmlsSchema):
    version_number: int = Field(ge=1)


class CourseGraphVersionResponse(AmlsSchema):
    id: UUID
    course_id: UUID
    version_number: int
    status: CourseGraphVersionStatus
    node_count: int
    edge_count: int
    built_at: datetime | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class CourseGraphVersionNodeCreate(AmlsSchema):
    course_node_id: UUID
    lecture_id: UUID | None = None


class CourseGraphVersionNodeResponse(AmlsSchema):
    id: UUID
    graph_version_id: UUID
    course_node_id: UUID
    lecture_id: UUID | None
    topological_rank: int | None
    created_at: datetime
    updated_at: datetime


class CourseGraphVersionEdgeCreate(AmlsSchema):
    prerequisite_course_node_id: UUID
    dependent_course_node_id: UUID


class CourseGraphVersionEdgeResponse(AmlsSchema):
    id: UUID
    graph_version_id: UUID
    prerequisite_course_node_id: UUID
    dependent_course_node_id: UUID
    created_at: datetime
    updated_at: datetime


class CourseGraphVersionDetailResponse(AmlsSchema):
    version: CourseGraphVersionResponse
    nodes: list[CourseGraphVersionNodeResponse]
    edges: list[CourseGraphVersionEdgeResponse]


class CourseWorkspaceNodeResponse(AmlsSchema):
    course_node_id: UUID
    problem_type_id: UUID | None
    name: str
    lecture_id: UUID | None
    has_lecture: bool
    topological_rank: int | None
    mastery_state: str
    is_frontier: bool


class CourseWorkspaceEdgeResponse(AmlsSchema):
    prerequisite_course_node_id: UUID
    dependent_course_node_id: UUID


class GraphAssessmentReviewSnapshotResponse(AmlsSchema):
    graph_assessment_id: UUID
    review_status: GraphAssessmentReviewStatus
    review_text: str | None
    review_recommendations: list[str]
    review_model: str | None
    review_error: str | None
    review_generated_at: datetime | None


class CourseWorkspaceActionFlagsResponse(AmlsSchema):
    can_start_entrance: bool
    can_start_practice: bool
    can_start_exam: bool
    can_start_mistakes: bool
    has_active_attempt: bool
    has_active_assessment: bool


class CourseWorkspaceAttemptResponse(AmlsSchema):
    id: UUID
    graph_version_id: UUID
    kind: TestAttemptKind
    status: TestAttemptStatus
    current_problem_id: UUID | None
    started_at: datetime | None
    paused_at: datetime | None
    total_paused_seconds: int
    elapsed_solve_seconds: int
    ended_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CourseWorkspaceResponse(AmlsSchema):
    course: CourseResponse
    graph_version: CourseGraphVersionResponse
    nodes: list[CourseWorkspaceNodeResponse]
    edges: list[CourseWorkspaceEdgeResponse]
    active_test_attempt: CourseWorkspaceAttemptResponse | None
    active_graph_assessment: GraphAssessmentResponse | None
    latest_graph_assessment: GraphAssessmentResponse | None
    latest_review: GraphAssessmentReviewSnapshotResponse | None
    action_flags: CourseWorkspaceActionFlagsResponse
