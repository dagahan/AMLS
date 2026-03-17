from uuid import UUID

from pydantic import Field

from src.pydantic_schemas.common import ThesisSchema


class TopicCreate(ThesisSchema):
    name: str = Field(min_length=1, max_length=255)


class TopicUpdate(ThesisSchema):
    name: str | None = Field(default=None, min_length=1, max_length=255)


class TopicResponse(ThesisSchema):
    id: UUID
    name: str


class SubtopicCreate(ThesisSchema):
    topic_id: UUID
    name: str = Field(min_length=1, max_length=255)


class SubtopicUpdate(ThesisSchema):
    topic_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)


class SubtopicResponse(ThesisSchema):
    id: UUID
    topic_id: UUID
    name: str
