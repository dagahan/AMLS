from uuid import UUID

from pydantic import Field

from src.models.pydantic.common import AmlsSchema


class DifficultyCreate(AmlsSchema):
    name: str = Field(min_length=1, max_length=255)
    coefficient: float = Field(gt=0)


class DifficultyUpdate(AmlsSchema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    coefficient: float | None = Field(default=None, gt=0)


class DifficultyResponse(AmlsSchema):
    id: UUID
    name: str
    coefficient: float
