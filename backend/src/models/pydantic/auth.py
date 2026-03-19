from pydantic import EmailStr, Field, SecretStr

from src.models.pydantic.common import AmlsSchema
from src.models.pydantic.user import UserResponse


class AccessPayload(AmlsSchema):
    sub: str
    sid: str
    exp: int


class RefreshPayload(AccessPayload):
    dsh: str


class SessionData(AmlsSchema):
    sub: str
    iat: int
    mtl: int
    dsh: str
    ish: str


class ClientContext(AmlsSchema):
    user_agent: str
    client_id: str
    local_system_time_zone: str
    platform: str
    ip: str


class RegisterRequest(AmlsSchema):
    email: EmailStr
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    password: SecretStr
    avatar_url: str | None = Field(default=None, max_length=500)


class LoginRequest(AmlsSchema):
    email: EmailStr
    password: SecretStr


class RefreshRequest(AmlsSchema):
    refresh_token: str = Field(min_length=1)


class ValidateAccessRequest(AmlsSchema):
    access_token: str = Field(min_length=1)


class AccessValidationResponse(AmlsSchema):
    valid: bool


class TokenPairResponse(AmlsSchema):
    access_token: str
    refresh_token: str


class AuthContext(AmlsSchema):
    user: UserResponse
    payload: AccessPayload


class AuthUserResponse(AmlsSchema):
    user: UserResponse
