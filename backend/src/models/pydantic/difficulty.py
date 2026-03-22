from src.storage.db.enums import DifficultyLevel
from src.models.pydantic.common import AmlsSchema


class DifficultyResponse(AmlsSchema):
    key: DifficultyLevel
    name: str
    coefficient: float
