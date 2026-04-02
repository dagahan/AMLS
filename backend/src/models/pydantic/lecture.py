from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from src.models.pydantic.common import AmlsSchema


class LectureCreate(AmlsSchema):
    title: str = Field(min_length=1, max_length=255)


class LectureResponse(AmlsSchema):
    id: UUID
    course_node_id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class LecturePageCreate(AmlsSchema):
    page_number: int = Field(ge=1)
    page_content: str = Field(min_length=1)


class LecturePageResponse(AmlsSchema):
    id: UUID
    lecture_id: UUID
    page_number: int
    page_content: str
    created_at: datetime
    updated_at: datetime


class LectureDetailResponse(AmlsSchema):
    lecture: LectureResponse
    pages: list[LecturePageResponse]
