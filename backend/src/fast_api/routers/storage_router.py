from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile

from src.fast_api.dependencies import ensure_admin_user, get_current_user
from src.models.pydantic.storage import UploadedImageResponse
from src.models.pydantic.user import UserResponse
from src.storage.storage_manager import StorageManager

if TYPE_CHECKING:
    from src.db.database import DataBase
    from src.models.alchemy import User


def get_storage_router(db: "DataBase") -> APIRouter:
    router = APIRouter(tags=["storage"])
    storage_manager = StorageManager(db)


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
        user: "User" = Depends(get_current_user),
    ) -> list[UploadedImageResponse]:
        ensure_admin_user(user)
        return await storage_manager.upload_problem_images(
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
        user: "User" = Depends(get_current_user),
    ) -> UserResponse:
        updated_user = await storage_manager.upload_profile_image(
            user_id=user.id,
            file=file,
            url_factory=lambda storage_key: build_file_url(request, storage_key),
        )
        return UserResponse.model_validate(updated_user)


    @router.get("/storage/files/{storage_key:path}", name="get_stored_file")
    async def get_stored_file(storage_key: str) -> Response:
        stored_file = await storage_manager.get_file(storage_key)
        return Response(content=stored_file.content, media_type=stored_file.content_type)


    return router
