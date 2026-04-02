from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from src.models.pydantic.common import AmlsSchema
from src.storage.db.enums import CourseGraphVersionStatus


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
