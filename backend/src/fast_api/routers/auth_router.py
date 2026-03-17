from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Request

from src.pydantic_schemas import (
    AccessValidationResponse,
    ClientContext,
    LoginRequest,
    RefreshRequest,
    TokenPairResponse,
    ValidateAccessRequest,
)
from src.services.auth.auth_service import AuthService

if TYPE_CHECKING:
    from src.db.database import DataBase


def get_auth_router(db: "DataBase") -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["auth"])
    auth_service = AuthService(db)


    def build_client_context(request: Request) -> ClientContext:
        return ClientContext(
            user_agent=request.headers.get("user-agent", "postman"),
            client_id=request.headers.get("x-client-id", "default-client"),
            local_system_time_zone=request.headers.get("x-time-zone", "UTC"),
            platform=request.headers.get("x-platform", "desktop"),
            ip=request.client.host if request.client is not None else "127.0.0.1",
        )


    @router.post("/login", response_model=TokenPairResponse, status_code=201)
    async def login(data: LoginRequest, request: Request) -> TokenPairResponse:
        client_context = build_client_context(request)
        return await auth_service.login_user(
            email=data.email,
            password=data.password.get_secret_value(),
            client_context=client_context,
        )


    @router.post("/refresh", response_model=TokenPairResponse, status_code=201)
    async def refresh(data: RefreshRequest) -> TokenPairResponse:
        return await auth_service.refresh_tokens(data.refresh_token)


    @router.post("/access/validate", response_model=AccessValidationResponse, status_code=200)
    async def validate_access(data: ValidateAccessRequest) -> AccessValidationResponse:
        is_valid = await auth_service.validate_access_token(data.access_token)
        return AccessValidationResponse(valid=is_valid)


    return router
