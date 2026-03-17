from pydantic import EmailStr, Field, SecretStr

from src.pydantic_schemas.common import ThesisSchema
from src.pydantic_schemas.user import UserResponse


class AccessPayload(ThesisSchema):
    sub: str
    sid: str
    exp: int


class RefreshPayload(AccessPayload):
    dsh: str


class SessionData(ThesisSchema):
    sub: str
    iat: int
    mtl: int
    dsh: str
    ish: str


class ClientContext(ThesisSchema):
    user_agent: str
    client_id: str
    local_system_time_zone: str
    platform: str
    ip: str


class RegisterRequest(ThesisSchema):
    email: EmailStr
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    password: SecretStr
    avatar_url: str | None = Field(default=None, max_length=500)


class LoginRequest(ThesisSchema):
    email: EmailStr
    password: SecretStr


class RefreshRequest(ThesisSchema):
    refresh_token: str = Field(min_length=1)


class ValidateAccessRequest(ThesisSchema):
    access_token: str = Field(min_length=1)


class AccessValidationResponse(ThesisSchema):
    valid: bool


class TokenPairResponse(ThesisSchema):
    access_token: str
    refresh_token: str


class AuthUserResponse(ThesisSchema):
    user: UserResponse
