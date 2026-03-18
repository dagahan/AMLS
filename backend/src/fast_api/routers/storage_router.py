from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile

from src.fast_api.dependencies import build_current_admin_dependency, build_current_user_dependency
from src.pydantic_schemas.storage import UploadedImageResponse
from src.pydantic_schemas.user import UserResponse
from src.services.storage_service import StorageService

if TYPE_CHECKING:
    from src.db.database import DataBase
    from src.db.models import User


def get_storage_router(db: "DataBase") -> APIRouter:
    router = APIRouter(tags=["storage"])
    current_admin = build_current_admin_dependency(db)
    current_user = build_current_user_dependency(db)
    storage_service = StorageService(db)


    def build_file_url(request: Request, storage_key: str) -> str:
        return str(request.url_for("get_stored_file", storage_key=storage_key))


    @router.post(
        "/admin/problem-images/upload",
        response_model=list[UploadedImageResponse],
        status_code=201,
    )
    async def upload_problem_images(
        request: Request,
        kind: Literal["condition", "solution"] = Form(...),
        files: list[UploadFile] = File(...),
        user: "User" = Depends(current_admin),
    ) -> list[UploadedImageResponse]:
        return await storage_service.upload_problem_images(
            user_id=str(user.id),
            kind=kind,
            files=files,
            url_factory=lambda storage_key: build_file_url(request, storage_key),
        )


    @router.post(
        "/storage/profile-image",
        response_model=UserResponse,
        status_code=201,
    )
    async def upload_profile_image(
        request: Request,
        file: UploadFile = File(...),
        user: "User" = Depends(current_user),
    ) -> UserResponse:
        updated_user = await storage_service.upload_profile_image(
            user_id=user.id,
            file=file,
            url_factory=lambda storage_key: build_file_url(request, storage_key),
        )
        return UserResponse.model_validate(updated_user)


    @router.get("/storage/files/{storage_key:path}", name="get_stored_file")
    async def get_stored_file(storage_key: str) -> Response:
        stored_file = await storage_service.get_file(storage_key)
        return Response(content=stored_file.content, media_type=stored_file.content_type)


    return router
