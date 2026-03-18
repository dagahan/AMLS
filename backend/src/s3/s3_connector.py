from __future__ import annotations
import mimetypes
import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from aiobotocore.session import get_session as get_s3_session
from botocore.config import Config
from src.core.utils import EnvTools, StringTools

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class S3Client:
    def __init__(self) -> None:
        self.bucket_name = EnvTools.required_load_env_var("S3_BUCKET_NAME")
        self.endpoint_url = EnvTools.required_load_env_var("S3_ENDPOINT_URL")
        self.region = EnvTools.required_load_env_var("S3_REGION")
        self.access_key = EnvTools.required_load_env_var("S3_ACCESS_KEY")
        self.secret_key = EnvTools.required_load_env_var("S3_SECRET_KEY")

        self.s3_session = get_s3_session()
        self.botocore_config = Config(
            region_name=self.region,
            s3={"addressing_style": "path"},
            retries={"max_attempts": 3, "mode": "standard"},
        )
        self.default_acl: str | None = None
        self.verify = int(EnvTools.required_load_env_var("S3_TLS_VERIFY")) == 1


    @asynccontextmanager
    async def get_s3_client(self) -> AsyncIterator[Any]:
        async with self.s3_session.create_client(
            "s3",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            endpoint_url=self.endpoint_url,
            config=self.botocore_config,
            verify=self.verify,
        ) as client:
            yield client


    @staticmethod
    def _ext_from(filename: str, content_type: str | None) -> str:
        ext = os.path.splitext(filename)[1]
        if not ext and content_type:
            guessed = mimetypes.guess_extension(content_type)
            if guessed:
                ext = guessed
        if not ext:
            ext = ".bin"
        return ext.lower()


    def make_key(self, prefix: str, user_id: str, filename: str, content_type: str | None) -> str:
        ext = self._ext_from(filename, content_type)
        safe_name = StringTools.hash_string(os.path.splitext(os.path.basename(filename))[0])[:12]
        suffix = uuid4().hex[:8]
        return f"{prefix}/{user_id}/{safe_name}-{suffix}{ext}"


    async def upload_bytes(
        self,
        data: bytes,
        s3_key: str,
        content_type: str | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {"Bucket": self.bucket_name, "Key": s3_key, "Body": data}
        if content_type:
            kwargs["ContentType"] = content_type
        if self.default_acl:
            kwargs["ACL"] = self.default_acl

        async with self.get_s3_client() as s3:
            await s3.put_object(**kwargs)


    async def delete_object(self, key: str) -> None:
        async with self.get_s3_client() as s3:
            await s3.delete_object(Bucket=self.bucket_name, Key=key)


    async def download_bytes(self, key: str) -> tuple[bytes, str | None]:
        async with self.get_s3_client() as s3:
            response = await s3.get_object(Bucket=self.bucket_name, Key=key)
            body = response["Body"]
            content = await body.read()
            content_type = response.get("ContentType")
            return content, content_type
