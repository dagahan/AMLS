from pydantic import BaseModel, ConfigDict


class ThesisSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class HealthResponse(ThesisSchema):
    status: str
    services: dict[str, str]


class MessageResponse(ThesisSchema):
    message: str
