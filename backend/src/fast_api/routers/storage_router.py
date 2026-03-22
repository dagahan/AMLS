from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile

from src.fast_api.dependencies import build_storage_file_url, require_role
from src.models.pydantic import AuthContext
from src.models.pydantic.storage import UploadedImageResponse
from src.models.pydantic.user import UserResponse
from src.storage.storage_manager import StorageManager
from src.storage.db.enums import UserRole


def get_storage_router(storage_manager: StorageManager) -> APIRouter:
    router = APIRouter(tags=["storage"])


    @router.post(
        "/admin/problem-images/upload",
        response_model=list[UploadedImageResponse],
        status_code=201,
    )
    async def upload_problem_images(
        request: Request,
        kind: Literal["condition", "solution"] = Form(...),
        files: list[UploadFile] = File(...),
        auth: AuthContext = Depends(require_role(role=UserRole.ADMIN)),
    ) -> list[UploadedImageResponse]:
        return await storage_manager.upload_problem_images(
            user_id=str(auth.user.id),
            kind=kind,
            files=files,
            url_factory=lambda storage_key: build_storage_file_url(request, storage_key),
        )


    @router.post(
        "/storage/profile-image",
        response_model=UserResponse,
        status_code=201,
    )
    async def upload_profile_image(
        request: Request,
        file: UploadFile = File(...),
        auth: AuthContext = Depends(require_role()),
    ) -> UserResponse:
        updated_user = await storage_manager.upload_profile_image(
            user_id=auth.user.id,
            file=file,
            url_factory=lambda storage_key: build_storage_file_url(request, storage_key),
        )
        return auth.user.model_copy(update={"avatar_url": updated_user.avatar_url})


    @router.get("/storage/files/{storage_key:path}", name="get_stored_file")
    async def get_stored_file(
        storage_key: str,
        auth: AuthContext = Depends(require_role()),
    ) -> Response:
        stored_file = await storage_manager.get_file(storage_key)
        return Response(content=stored_file.content, media_type=stored_file.content_type)


    return router
