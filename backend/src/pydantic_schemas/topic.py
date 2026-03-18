from uuid import UUID

from pydantic import Field

from src.pydantic_schemas.common import AmlsSchema


class TopicCreate(AmlsSchema):
    name: str = Field(min_length=1, max_length=255)


class TopicUpdate(AmlsSchema):
    name: str | None = Field(default=None, min_length=1, max_length=255)


class TopicResponse(AmlsSchema):
    id: UUID
    name: str


class SubtopicCreate(AmlsSchema):
    topic_id: UUID
    name: str = Field(min_length=1, max_length=255)


class SubtopicUpdate(AmlsSchema):
    topic_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)


class SubtopicResponse(AmlsSchema):
    id: UUID
    topic_id: UUID
    name: str
