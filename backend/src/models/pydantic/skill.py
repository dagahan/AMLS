from uuid import UUID

from pydantic import Field

from src.models.pydantic.common import AmlsSchema


class SkillCreate(AmlsSchema):
    name: str = Field(min_length=1, max_length=255)


class SkillUpdate(AmlsSchema):
    name: str | None = Field(default=None, min_length=1, max_length=255)


class SkillResponse(AmlsSchema):
    id: UUID
    name: str


class SubskillCreate(AmlsSchema):
    skill_id: UUID
    name: str = Field(min_length=1, max_length=255)


class SubskillUpdate(AmlsSchema):
    skill_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)


class SubskillResponse(AmlsSchema):
    id: UUID
    skill_id: UUID
    name: str
