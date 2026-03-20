from __future__ import annotations

from uuid import UUID

from pydantic import Field, model_validator

from src.models.pydantic.common import AmlsSchema


class ProblemTypeCreate(AmlsSchema):
    name: str = Field(min_length=1, max_length=255)
    prerequisite_ids: list[UUID] = Field(default_factory=list)


    @model_validator(mode="after")
    def validate_payload(self) -> "ProblemTypeCreate":
        validate_prerequisite_ids(self.prerequisite_ids)
        return self


class ProblemTypeUpdate(AmlsSchema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    prerequisite_ids: list[UUID] | None = None


    @model_validator(mode="after")
    def validate_payload(self) -> "ProblemTypeUpdate":
        if self.prerequisite_ids is not None:
            validate_prerequisite_ids(self.prerequisite_ids)
        return self


class ProblemTypeResponse(AmlsSchema):
    id: UUID
    name: str
    prerequisite_ids: list[UUID]


class ProblemTypeGraphNodeResponse(AmlsSchema):
    id: UUID
    name: str
    prerequisite_ids: list[UUID] = Field(default_factory=list)
    children: list["ProblemTypeGraphNodeResponse"] = Field(default_factory=list)


class ProblemTypeGraphResponse(AmlsSchema):
    roots: list[ProblemTypeGraphNodeResponse]


def validate_prerequisite_ids(prerequisite_ids: list[UUID]) -> None:
    if len(set(prerequisite_ids)) != len(prerequisite_ids):
        raise ValueError("Problem type prerequisites must be unique")
