from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Literal

from fastapi import HTTPException, UploadFile, status

from src.models.alchemy import User
from src.models.pydantic.storage import UploadedImageResponse
from src.models.pydantic.storage import StoredFile
from src.models.pydantic.user import AvatarSnapshot
from src.s3.s3_connector import S3Client
from src.transaction_manager.transaction_manager import execute_atomic_step, transactional

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from src.db.database import DataBase


class ImageUploader:
    def __init__(self, db: "DataBase") -> None:
        self.db = db
        self._s3_client: S3Client | None = None


    @property
    def s3_client(self) -> S3Client:
        if self._s3_client is None:
            self._s3_client = S3Client()
        return self._s3_client


    @transactional
    async def upload_problem_images(
        self,
        user_id: str,
        kind: Literal["condition", "solution"],
        files: Sequence[UploadFile],
        url_factory: "Callable[[str], str]",
    ) -> list[UploadedImageResponse]:
        uploaded_images: list[UploadedImageResponse] = []

        for file in files:
            async def upload_current_file() -> UploadedImageResponse:
                return await self._upload_single_file(
                    prefix=f"problems/{kind}",
                    user_id=user_id,
                    file=file,
                    url_factory=url_factory,
                )

            uploaded_image = await execute_atomic_step(
                action=upload_current_file,
                rollback=lambda uploaded_image: self._delete_uploaded_image(uploaded_image.key),
                step_name="upload_problem_image",
            )
            uploaded_images.append(uploaded_image)

        return uploaded_images


    @transactional
    async def upload_profile_image(
        self,
        user_id: uuid.UUID,
        file: UploadFile,
        url_factory: "Callable[[str], str]",
    ) -> User:
        uploaded_image = await execute_atomic_step(
            action=lambda: self._upload_single_file(
                prefix="users/avatars",
                user_id=str(user_id),
                file=file,
                url_factory=url_factory,
            ),
            rollback=lambda uploaded_image: self._delete_uploaded_image(uploaded_image.key),
            step_name="upload_profile_image",
        )

        await execute_atomic_step(
            action=lambda: self._set_user_avatar(user_id, uploaded_image.url),
            rollback=self._restore_user_avatar,
            step_name="update_profile_image",
        )
        return await self.get_user_or_404(user_id)


    async def get_file(self, key: str) -> StoredFile:
        content, content_type = await self.s3_client.download_bytes(key)
        return StoredFile(content=content, content_type=content_type)


    async def _upload_single_file(
        self,
        prefix: str,
        user_id: str,
        file: UploadFile,
        url_factory: "Callable[[str], str]",
    ) -> UploadedImageResponse:
        content = await file.read()
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty",
            )

        key = self.s3_client.make_key(
            prefix=prefix,
            user_id=user_id,
            filename=file.filename or "file",
            content_type=file.content_type,
        )
        await self.s3_client.upload_bytes(content, key, file.content_type)
        return UploadedImageResponse(key=key, url=url_factory(key))


    async def _delete_uploaded_image(self, key: str) -> None:
        await self.s3_client.delete_object(key)


    async def _set_user_avatar(self, user_id: uuid.UUID, avatar_url: str) -> AvatarSnapshot:
        async with self.db.session_ctx() as session:
            user = await session.get(User, user_id)
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found",
                )

            snapshot = AvatarSnapshot(user_id=user.id, avatar_url=user.avatar_url)
            user.avatar_url = avatar_url
            await session.flush()
            return snapshot


    async def _restore_user_avatar(self, snapshot: AvatarSnapshot) -> None:
        async with self.db.session_ctx() as session:
            user = await session.get(User, snapshot.user_id)
            if user is None:
                return

            user.avatar_url = snapshot.avatar_url
            await session.flush()


    async def get_user_or_404(self, user_id: uuid.UUID) -> User:
        async with self.db.session_ctx() as session:
            user = await session.get(User, user_id)
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found",
                )
            return user
