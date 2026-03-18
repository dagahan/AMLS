from uuid import UUID

from src.db.enums import UserRole
from src.models.pydantic.common import AmlsSchema


class UserResponse(AmlsSchema):
    id: UUID
    email: str
    first_name: str
    last_name: str
    avatar_url: str | None
    role: UserRole
    is_active: bool


class AvatarSnapshot(AmlsSchema):
    user_id: UUID
    avatar_url: str | None
