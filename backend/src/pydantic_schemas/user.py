from uuid import UUID

from src.db.enums import UserRole
from src.pydantic_schemas.common import AmlsSchema


class UserResponse(AmlsSchema):
    id: UUID
    email: str
    first_name: str
    last_name: str
    avatar_url: str | None
    role: UserRole
    is_active: bool
