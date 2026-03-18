from src.pydantic_schemas.common import AmlsSchema


class UploadedImageResponse(AmlsSchema):
    key: str
    url: str


class StoredFile(AmlsSchema):
    content: bytes
    content_type: str | None
