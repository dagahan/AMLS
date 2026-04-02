from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Literal

from src.core.logging import get_logger
from src.models.alchemy import User
from src.models.pydantic.storage import StoredFile, UploadedImageResponse
from src.storage.db.database import DataBase
from src.storage.image_uploader import ImageUploader
from src.storage.s3.s3_connector import S3Client
from src.storage.valkey.valkey_client import get_async_valkey_client, get_valkey_client

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Sequence

    from fastapi import UploadFile
    from sqlalchemy.ext.asyncio import AsyncSession
    from valkey import Valkey
    from valkey.asyncio import Valkey as AsyncValkey


logger = get_logger(__name__)


class StorageManager:
    def __init__(self) -> None:
        self._database = DataBase()
        self._sync_valkey_client: Valkey | None = None
        self._s3_client: S3Client | None = None
        self._image_uploader: ImageUploader | None = None
        logger.info("Created storage manager")


    async def connect(self) -> None:
        logger.info("Initializing storage manager database connection")
        await self._database.init_alchemy_engine()
        logger.info("Storage manager database connection is ready")


    async def close(self) -> None:
        logger.info("Closing storage manager resources")
        await self._database.dispose()
        logger.info("Closed storage manager resources")


    def get_db_session(self) -> AsyncIterator[AsyncSession]:
        logger.debug("Creating database session iterator from storage manager")
        return self._database.get_session()


    @asynccontextmanager
    async def session_ctx(self) -> AsyncIterator[AsyncSession]:
        logger.debug("Opening database session context from storage manager")
        async with self._database.session_ctx() as session:
            yield session


    def get_valkey_sync(self) -> Valkey:
        if self._sync_valkey_client is None:
            logger.info("Initializing synchronous Valkey client")
            self._sync_valkey_client = get_valkey_client()
        else:
            logger.debug("Reusing synchronous Valkey client")
        return self._sync_valkey_client


    def get_valkey_async(self) -> AsyncValkey:
        logger.debug("Retrieving asynchronous Valkey client")
        return get_async_valkey_client()


    def get_s3_client(self) -> S3Client:
        if self._s3_client is None:
            logger.info("Initializing S3 client")
            self._s3_client = S3Client()
        else:
            logger.debug("Reusing S3 client")
        return self._s3_client


    async def check_database(self) -> bool:
        logger.debug("Running database health check")
        is_healthy = await self._database.test_connection()
        logger.info("Finished database health check: is_healthy={}", is_healthy)
        return is_healthy


    def check_valkey(self) -> bool:
        try:
            is_healthy = bool(self.get_valkey_sync().ping())
            logger.info("Finished Valkey health check: is_healthy={}", is_healthy)
            return is_healthy
        except Exception:
            logger.warning("Valkey health check failed")
            return False


    async def upload_problem_images(
        self,
        user_id: str,
        kind: Literal["condition", "solution"],
        files: Sequence[UploadFile],
        url_factory: Callable[[str], str],
    ) -> list[UploadedImageResponse]:
        logger.info(
            "Uploading problem images: user_id={}, kind={}, file_count={}",
            user_id,
            kind,
            len(files),
        )
        uploaded_images = await self._get_image_uploader().upload_problem_images(
            user_id=user_id,
            kind=kind,
            files=files,
            url_factory=url_factory,
        )
        logger.info(
            "Uploaded problem images: user_id={}, kind={}, file_count={}",
            user_id,
            kind,
            len(uploaded_images),
        )
        return uploaded_images


    async def upload_profile_image(
        self,
        user_id: uuid.UUID,
        file: UploadFile,
        url_factory: Callable[[str], str],
    ) -> User:
        logger.info(
            "Uploading profile image: user_id={}, filename={}",
            user_id,
            file.filename,
        )
        updated_user = await self._get_image_uploader().upload_profile_image(
            user_id=user_id,
            file=file,
            url_factory=url_factory,
        )
        logger.info("Uploaded profile image: user_id={}", user_id)
        return updated_user


    async def get_file(self, key: str) -> StoredFile:
        logger.info("Fetching stored file: key={}", key)
        stored_file = await self._get_image_uploader().get_file(key)
        logger.info(
            "Fetched stored file: key={}, content_type={}, size={}",
            key,
            stored_file.content_type,
            len(stored_file.content),
        )
        return stored_file


    def _get_image_uploader(self) -> ImageUploader:
        if self._image_uploader is None:
            logger.info("Initializing image uploader")
            self._image_uploader = ImageUploader(self)
        else:
            logger.debug("Reusing image uploader")
        return self._image_uploader
