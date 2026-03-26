from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Literal

from src.models.alchemy import User
from src.models.pydantic.storage import StoredFile, UploadedImageResponse
from src.storage.db.database import DataBase
from src.storage.image_uploader import ImageUploader
from src.storage.s3.s3_connector import S3Client
from src.storage.valkey.entrance_test_runtime import EntranceTestRuntimeStorage
from src.storage.valkey.valkey_client import get_async_valkey_client, get_valkey_client

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Sequence

    from fastapi import UploadFile
    from sqlalchemy.ext.asyncio import AsyncSession
    from valkey import Valkey
    from valkey.asyncio import Valkey as AsyncValkey


class StorageManager:
    def __init__(self, database: DataBase | None = None) -> None:
        self._database = database or DataBase()
        self._sync_valkey_client: Valkey | None = None
        self._s3_client: S3Client | None = None
        self._entrance_test_runtime_storage: EntranceTestRuntimeStorage | None = None
        self._image_uploader: ImageUploader | None = None


    async def connect(self) -> None:
        await self._database.init_alchemy_engine()


    async def close(self) -> None:
        await self._database.dispose()


    def get_database(self) -> DataBase:
        return self._database


    def get_db_session(self) -> AsyncIterator[AsyncSession]:
        return self._database.get_session()


    @asynccontextmanager
    async def session_ctx(self) -> AsyncIterator[AsyncSession]:
        async with self._database.session_ctx() as session:
            yield session


    def get_valkey_sync(self) -> Valkey:
        if self._sync_valkey_client is None:
            self._sync_valkey_client = get_valkey_client()
        return self._sync_valkey_client


    def get_valkey_async(self) -> AsyncValkey:
        return get_async_valkey_client()


    def get_s3_client(self) -> S3Client:
        if self._s3_client is None:
            self._s3_client = S3Client()
        return self._s3_client


    def get_entrance_test_runtime_storage(self) -> EntranceTestRuntimeStorage:
        if self._entrance_test_runtime_storage is None:
            self._entrance_test_runtime_storage = EntranceTestRuntimeStorage(
                valkey_client_factory=self.get_valkey_async,
            )
        return self._entrance_test_runtime_storage


    async def check_database(self) -> bool:
        return await self._database.test_connection()


    def check_valkey(self) -> bool:
        try:
            return bool(self.get_valkey_sync().ping())
        except Exception:
            return False


    async def upload_problem_images(
        self,
        user_id: str,
        kind: Literal["condition", "solution"],
        files: Sequence[UploadFile],
        url_factory: Callable[[str], str],
    ) -> list[UploadedImageResponse]:
        return await self._get_image_uploader().upload_problem_images(
            user_id=user_id,
            kind=kind,
            files=files,
            url_factory=url_factory,
        )


    async def upload_profile_image(
        self,
        user_id: uuid.UUID,
        file: UploadFile,
        url_factory: Callable[[str], str],
    ) -> User:
        return await self._get_image_uploader().upload_profile_image(
            user_id=user_id,
            file=file,
            url_factory=url_factory,
        )


    async def get_file(self, key: str) -> StoredFile:
        return await self._get_image_uploader().get_file(key)


    def _get_image_uploader(self) -> ImageUploader:
        if self._image_uploader is None:
            self._image_uploader = ImageUploader(self)
        return self._image_uploader
