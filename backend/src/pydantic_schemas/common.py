from pydantic import BaseModel, ConfigDict


class AmlsSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class HealthResponse(AmlsSchema):
    status: str
    services: dict[str, str]


class MessageResponse(AmlsSchema):
    message: str
