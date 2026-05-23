from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from app.core.config import settings


class LocalSyncStorage:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def build_key(self, workspace_id: uuid.UUID, file_id: uuid.UUID, version: int, checksum_sha256: str) -> str:
        return f"{workspace_id}/{file_id}/{version}-{checksum_sha256}.md"

    def write(self, storage_key: str, content: bytes) -> None:
        path = self._path_for_key(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def read(self, storage_key: str) -> bytes:
        return self._path_for_key(storage_key).read_bytes()

    def exists(self, storage_key: str) -> bool:
        return self._path_for_key(storage_key).is_file()

    def _path_for_key(self, storage_key: str) -> Path:
        parts = storage_key.split("/")
        if not parts or any(part in {"", ".", ".."} for part in parts):
            raise ValueError("storage_key must be relative and cannot contain empty or parent segments")
        path = (self.root / storage_key).resolve()
        root = self.root.resolve()
        if root != path and root not in path.parents:
            raise ValueError("storage_key escapes sync storage root")
        return path


class S3SyncStorage:
    def __init__(
        self,
        bucket: str,
        region: str,
        endpoint_url: str = "",
        access_key_id: str = "",
        secret_access_key: str = "",
    ):
        if not bucket:
            raise ValueError("S3 bucket is required")
        try:
            import boto3
        except ModuleNotFoundError as exc:
            raise RuntimeError("boto3 is required when SYNC_STORAGE_BACKEND=s3") from exc

        client_kwargs = {"region_name": region}
        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url
        if access_key_id and secret_access_key:
            client_kwargs["aws_access_key_id"] = access_key_id
            client_kwargs["aws_secret_access_key"] = secret_access_key

        self.bucket = bucket
        self.client = boto3.client("s3", **client_kwargs)

    def build_key(self, workspace_id: uuid.UUID, file_id: uuid.UUID, version: int, checksum_sha256: str) -> str:
        return f"{workspace_id}/{file_id}/{version}-{checksum_sha256}.md"

    def write(self, storage_key: str, content: bytes) -> None:
        self._validate_key(storage_key)
        self.client.put_object(
            Bucket=self.bucket,
            Key=storage_key,
            Body=content,
            ContentType="application/octet-stream",
            ServerSideEncryption="AES256",
        )

    def read(self, storage_key: str) -> bytes:
        self._validate_key(storage_key)
        response = self.client.get_object(Bucket=self.bucket, Key=storage_key)
        return response["Body"].read()

    def exists(self, storage_key: str) -> bool:
        self._validate_key(storage_key)
        try:
            self.client.head_object(Bucket=self.bucket, Key=storage_key)
            return True
        except Exception as exc:
            response = getattr(exc, "response", {})
            status_code = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status_code == 404:
                return False
            raise

    def _validate_key(self, storage_key: str) -> None:
        parts = storage_key.split("/")
        if not parts or any(part in {"", ".", ".."} for part in parts):
            raise ValueError("storage_key must be relative and cannot contain empty or parent segments")


def get_sync_storage():
    if settings.SYNC_STORAGE_BACKEND == "s3":
        return S3SyncStorage(
            bucket=settings.S3_BUCKET,
            region=settings.S3_REGION,
            endpoint_url=settings.S3_ENDPOINT_URL,
            access_key_id=settings.S3_ACCESS_KEY_ID,
            secret_access_key=settings.S3_SECRET_ACCESS_KEY,
        )
    return LocalSyncStorage(settings.SYNC_STORAGE_ROOT)


def checksum_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
