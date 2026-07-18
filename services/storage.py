from __future__ import annotations

import json
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
        if self.settings.storage_backend == "s3" and self.settings.s3_endpoint_url:
            upload_url = self._presign_put(object_key, content_type)
        else:
            upload_url = f"{self.settings.public_api_base}/api/v1/uploads/{upload_id}/content"
        return upload_id, upload_url, object_key

    def _presign_put(self, object_key: str, content_type: str) -> str:
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("boto3 is required for S3 storage") from exc

        client = boto3.client(
            "s3",
            endpoint_url=self.settings.s3_endpoint_url,
            aws_access_key_id=self.settings.s3_access_key,
            aws_secret_access_key=self.settings.s3_secret_key,
            region_name=self.settings.s3_region,
        )
        return client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.settings.s3_bucket,
                "Key": object_key,
                "ContentType": content_type,
            },
            ExpiresIn=3600,
        )

    def save_local(self, object_key: str, stream: BinaryIO) -> Path:
        path = self.root / object_key
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
        return path

    def resolve_path(self, object_key: str) -> Path:
        path = self.root / object_key
        if not path.exists():
            raise FileNotFoundError(object_key)
        return path

    def write_json(self, object_key: str, payload: dict) -> Path:
        path = self.root / object_key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return path

    def read_text(self, object_key: str) -> str:
        return self.resolve_path(object_key).read_text(encoding="utf-8", errors="ignore")
