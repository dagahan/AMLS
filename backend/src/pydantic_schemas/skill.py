from uuid import UUID

from pydantic import Field

from src.pydantic_schemas.common import ThesisSchema


class SkillCreate(ThesisSchema):
    name: str = Field(min_length=1, max_length=255)


class SkillUpdate(ThesisSchema):
    name: str | None = Field(default=None, min_length=1, max_length=255)


class SkillResponse(ThesisSchema):
    id: UUID
    name: str


class SubskillCreate(ThesisSchema):
    skill_id: UUID
    name: str = Field(min_length=1, max_length=255)


class SubskillUpdate(ThesisSchema):
    skill_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)


class SubskillResponse(ThesisSchema):
    id: UUID
    skill_id: UUID
    name: str
