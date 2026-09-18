"""Cloudflare R2 Object Storage Provider.

Connects to Cloudflare R2 via boto3 S3-compatible client.
All blocking network calls are delegated to the dedicated I/O ThreadPoolExecutor
via run_in_io_thread to ensure zero event-loop starvation (Bulkhead Pattern).
"""

from __future__ import annotations

import logging
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.services.repository.executor import run_in_io_thread
from app.services.storage.base import StorageError, StorageNotFoundError, StorageProvider

logger = logging.getLogger("fussion.storage.r2")


class R2StorageProvider(StorageProvider):
    """Cloudflare R2 storage provider backed by boto3 S3 client."""

    def __init__(
        self,
        *,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str,
        endpoint_url: str | None = None,
        public_url: str | None = None,
    ) -> None:
        self.account_id = account_id
        self.bucket_name = bucket_name
        self.public_url = public_url.rstrip("/") if public_url else None

        endpoint = endpoint_url or f"https://{account_id}.r2.cloudflarestorage.com"
        self.endpoint_url = endpoint.rstrip("/")

        # Cloudflare R2 requires AWS SigV4
        config = Config(
            signature_version="s3v4",
            retries={"max_attempts": 3, "mode": "standard"},
        )

        self._s3 = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name="auto",
            config=config,
        )

    def _sync_upload(
        self,
        key: str,
        data: bytes,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> str:
        try:
            extra_args: dict[str, Any] = {
                "Bucket": self.bucket_name,
                "Key": key,
                "Body": data,
                "ContentType": content_type,
            }
            if metadata:
                extra_args["Metadata"] = metadata

            self._s3.put_object(**extra_args)

            if self.public_url:
                return f"{self.public_url}/{key}"
            return f"r2://{self.bucket_name}/{key}"
        except ClientError as exc:
            logger.error("R2 upload error for key %s: %s", key, exc)
            raise StorageError(f"Failed to upload {key} to R2: {exc}") from exc

    async def upload(
        self,
        key: str,
        data: bytes,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> str:
        return await run_in_io_thread(
            self._sync_upload,
            key,
            data,
            content_type,
            metadata,
        )

    def _sync_download(self, key: str) -> bytes:
        try:
            resp = self._s3.get_object(Bucket=self.bucket_name, Key=key)
            body = resp["Body"]
            return body.read()
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("NoSuchKey", "404"):
                raise StorageNotFoundError(f"Object {key} not found in R2") from exc
            logger.error("R2 download error for key %s: %s", key, exc)
            raise StorageError(f"Failed to download {key} from R2: {exc}") from exc

    async def download(self, key: str) -> bytes:
        return await run_in_io_thread(self._sync_download, key)

    def _sync_delete(self, key: str) -> None:
        try:
            self._s3.delete_object(Bucket=self.bucket_name, Key=key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("NoSuchKey", "404"):
                return
            logger.warning("R2 delete warning for key %s: %s", key, exc)
            raise StorageError(f"Failed to delete {key} from R2: {exc}") from exc

    async def delete(self, key: str) -> None:
        await run_in_io_thread(self._sync_delete, key)

    def _sync_exists(self, key: str) -> bool:
        try:
            self._s3.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("NoSuchKey", "404"):
                return False
            logger.error("R2 head error for key %s: %s", key, exc)
            raise StorageError(f"Failed to check existence of {key} in R2: {exc}") from exc

    async def exists(self, key: str) -> bool:
        return await run_in_io_thread(self._sync_exists, key)

    def _sync_get_url(self, key: str, expires_in: int = 3600) -> str:
        if self.public_url:
            return f"{self.public_url}/{key}"
        try:
            return self._s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": key},
                ExpiresIn=expires_in,
            )
        except ClientError as exc:
            logger.error("R2 presigned URL generation error for key %s: %s", key, exc)
            raise StorageError(f"Failed to generate presigned URL for {key}: {exc}") from exc

    async def get_url(self, key: str, expires_in: int = 3600) -> str:
        return await run_in_io_thread(self._sync_get_url, key, expires_in)
