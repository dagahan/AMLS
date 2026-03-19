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
