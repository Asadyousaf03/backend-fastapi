from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path
from typing import BinaryIO

from config import Settings, get_settings


class StorageService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.root = Path(self.settings.local_storage_path)
        self.root.mkdir(parents=True, exist_ok=True)

    def create_upload_slot(
        self,
        filename: str,
        content_type: str,
        size_bytes: int,
    ) -> tuple[str, str, str]:
        upload_id = str(uuid.uuid4())
        safe_name = Path(filename).name.replace(" ", "_")
        object_key = f"uploads/{upload_id}/{safe_name}"
        # Always proxy content through the API so the browser never needs
        # direct S3/CORS access. A relative path lets the frontend prefix it
        # with NEXT_PUBLIC_API_URL regardless of PUBLIC_API_BASE.
        upload_url = f"/api/v2/uploads/{upload_id}/content"
        return upload_id, upload_url, object_key

    def _s3_client(self):
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise RuntimeError("boto3 is required for S3 storage") from exc
        # Supabase (and many S3-compatible stores) require path-style URLs.
        return boto3.client(
            "s3",
            endpoint_url=self.settings.s3_endpoint_url,
            aws_access_key_id=self.settings.s3_access_key,
            aws_secret_access_key=self.settings.s3_secret_key,
            region_name=self.settings.s3_region,
            config=Config(s3={"addressing_style": "path"}, signature_version="s3v4"),
        )

    def _presign_put(self, object_key: str, content_type: str) -> str:
        client = self._s3_client()
        return client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.settings.s3_bucket,
                "Key": object_key,
                "ContentType": content_type,
            },
            ExpiresIn=3600,
        )

    def exists(self, object_key: str) -> bool:
        if self.settings.storage_backend == "s3" and self.settings.s3_endpoint_url:
            client = self._s3_client()
            try:
                client.head_object(Bucket=self.settings.s3_bucket, Key=object_key)
                return True
            except Exception:
                return False
        return (self.root / object_key).exists()

    def save_upload(
        self,
        object_key: str,
        stream: BinaryIO,
        *,
        expected_bytes: int,
        max_bytes: int,
    ) -> int:
        """Persist an uploaded stream to the active backend (local or S3).

        Streams to a temp file with size validation, then either moves it into
        local storage or uploads it to the S3-compatible bucket server-side.
        """
        tmp = Path(tempfile.gettempdir()) / "genomic-ast-uploads" / object_key
        tmp.parent.mkdir(parents=True, exist_ok=True)
        bytes_written = 0
        try:
            with tmp.open("wb") as handle:
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    bytes_written += len(chunk)
                    if bytes_written > max_bytes:
                        raise ValueError("Uploaded file exceeds maximum size")
                    handle.write(chunk)
            if bytes_written != expected_bytes:
                raise ValueError(
                    f"Uploaded size ({bytes_written}) does not match declared size "
                    f"({expected_bytes})"
                )
            if self.settings.storage_backend == "s3" and self.settings.s3_endpoint_url:
                client = self._s3_client()
                client.upload_file(str(tmp), self.settings.s3_bucket, object_key)
            else:
                dest = self.root / object_key
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(tmp.read_bytes())
        finally:
            tmp.unlink(missing_ok=True)
        return bytes_written

    def save_local(
        self,
        object_key: str,
        stream: BinaryIO,
        *,
        expected_bytes: int,
        max_bytes: int,
    ) -> tuple[Path, int]:
        path = self.root / object_key
        path.parent.mkdir(parents=True, exist_ok=True)
        bytes_written = 0
        try:
            with path.open("wb") as handle:
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    bytes_written += len(chunk)
                    if bytes_written > max_bytes:
                        raise ValueError("Uploaded file exceeds maximum size")
                    handle.write(chunk)
            if bytes_written != expected_bytes:
                raise ValueError(
                    f"Uploaded size ({bytes_written}) does not match declared size "
                    f"({expected_bytes})"
                )
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return path, bytes_written

    def resolve_path(self, object_key: str) -> Path:
        path = self.root / object_key
        if not path.exists():
            raise FileNotFoundError(object_key)
        return path

    def download_to(self, object_key: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if self.settings.storage_backend == "s3" and self.settings.s3_endpoint_url:
            client = self._s3_client()
            client.download_file(self.settings.s3_bucket, object_key, str(destination))
            return destination
        source = self.resolve_path(object_key)
        destination.write_bytes(source.read_bytes())
        return destination

    def ensure_local(self, object_key: str) -> Path:
        if self.settings.storage_backend == "s3" and self.settings.s3_endpoint_url:
            tmp = Path(tempfile.gettempdir()) / "genomic-ast" / object_key
            return self.download_to(object_key, tmp)
        return self.resolve_path(object_key)

    def write_bytes(self, object_key: str, data: bytes) -> str:
        if self.settings.storage_backend == "s3" and self.settings.s3_endpoint_url:
            client = self._s3_client()
            client.put_object(
                Bucket=self.settings.s3_bucket,
                Key=object_key,
                Body=data,
            )
            return object_key
        path = self.root / object_key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return object_key

    def write_json(self, object_key: str, payload: dict) -> str:
        data = json.dumps(payload, indent=2, default=str).encode("utf-8")
        return self.write_bytes(object_key, data)

    def read_text(self, object_key: str) -> str:
        if self.settings.storage_backend == "s3" and self.settings.s3_endpoint_url:
            client = self._s3_client()
            obj = client.get_object(Bucket=self.settings.s3_bucket, Key=object_key)
            return obj["Body"].read().decode("utf-8", errors="ignore")
        return self.resolve_path(object_key).read_text(encoding="utf-8", errors="ignore")
