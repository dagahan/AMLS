from uuid import UUID

from pydantic import Field

from src.pydantic_schemas.common import ThesisSchema


class DifficultyCreate(ThesisSchema):
    name: str = Field(min_length=1, max_length=255)
    coefficient_beta_bernoulli: float = Field(gt=0)


class DifficultyUpdate(ThesisSchema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    coefficient_beta_bernoulli: float | None = Field(default=None, gt=0)


class DifficultyResponse(ThesisSchema):
    id: UUID
    name: str
    coefficient_beta_bernoulli: float
