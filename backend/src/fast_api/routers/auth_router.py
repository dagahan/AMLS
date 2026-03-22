from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from src.fast_api.dependencies import build_client_context, require_role
from src.models.pydantic import (
    AccessValidationResponse,
    AuthContext,
    AuthUserResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPairResponse,
    UserResponse,
    ValidateAccessRequest,
    build_user_response,
)
from src.services.auth.auth_service import AuthService
from src.storage.storage_manager import StorageManager


def get_auth_router(storage_manager: StorageManager) -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["auth"])
    auth_service = AuthService(storage_manager)


    @router.post("/register", response_model=UserResponse, status_code=201)
    async def register(data: RegisterRequest) -> UserResponse:
        user = await auth_service.register_user(data)
        return build_user_response(user)


    @router.post("/login", response_model=TokenPairResponse, status_code=201)
    async def login(data: LoginRequest, request: Request) -> TokenPairResponse:
        client_context = build_client_context(request)
        return await auth_service.login_user(
            email=str(data.email),
            password=data.password.get_secret_value(),
            client_context=client_context,
        )


    @router.post("/refresh", response_model=TokenPairResponse, status_code=201)
    async def refresh(data: RefreshRequest) -> TokenPairResponse:
        return await auth_service.refresh_tokens(data.refresh_token)


    @router.post("/access/validate", response_model=AccessValidationResponse, status_code=200)
    async def validate_access(data: ValidateAccessRequest) -> AccessValidationResponse:
        await auth_service.validate_access_token(data.access_token)
        return AccessValidationResponse(valid=True)


    @router.get("/me", response_model=AuthUserResponse, status_code=200)
    async def get_me(auth: AuthContext = Depends(require_role())) -> AuthUserResponse:
        return AuthUserResponse(user=auth.user)


    return router
