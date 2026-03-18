from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Literal

from src.models.pydantic.storage import StoredFile
from src.storage.image_uploader import ImageUploader

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from fastapi import UploadFile

    from src.db.database import DataBase
    from src.models.alchemy import User
    from src.models.pydantic.storage import UploadedImageResponse


class StorageManager:
    def __init__(self, db: "DataBase") -> None:
        self.image_uploader = ImageUploader(db)


    async def upload_problem_images(
        self,
        user_id: str,
        kind: Literal["condition", "solution"],
        files: "Sequence[UploadFile]",
        url_factory: "Callable[[str], str]",
    ) -> list["UploadedImageResponse"]:
        return await self.image_uploader.upload_problem_images(
            user_id=user_id,
            kind=kind,
            files=files,
            url_factory=url_factory,
        )


    async def upload_profile_image(
        self,
        user_id: uuid.UUID,
        file: "UploadFile",
        url_factory: "Callable[[str], str]",
    ) -> "User":
        return await self.image_uploader.upload_profile_image(
            user_id=user_id,
            file=file,
            url_factory=url_factory,
        )


    async def get_file(self, key: str) -> StoredFile:
        return await self.image_uploader.get_file(key)
