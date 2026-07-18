from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from config import get_settings
from db.models import UploadRecord
from db.session import get_db
from schemas import ErrorResponse, UploadRequest, UploadResponse
from services.storage import StorageService

router = APIRouter(prefix="/api/v1", tags=["uploads"])


@router.post(
    "/uploads",
    response_model=UploadResponse,
    responses={400: {"model": ErrorResponse}},
)
def create_upload(
    payload: UploadRequest,
    db: Session = Depends(get_db),
) -> UploadResponse:
    settings = get_settings()
    if payload.size_bytes > settings.max_upload_bytes:
        raise HTTPException(status_code=400, detail="File exceeds maximum upload size")

    storage = StorageService(settings)
    upload_id, upload_url, object_key = storage.create_upload_slot(
        payload.filename,
        payload.content_type,
        payload.size_bytes,
    )
    record = UploadRecord(
        id=upload_id,
        filename=payload.filename,
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
        object_key=object_key,
        sample_json=payload.metadata.model_dump_json(),
    )
    db.add(record)
    db.commit()

    return UploadResponse(
        upload_id=upload_id,
        upload_url=upload_url,
        object_key=object_key,
        expires_in_seconds=3600,
    )


@router.put(
    "/uploads/{upload_id}/content",
    status_code=204,
    responses={404: {"model": ErrorResponse}},
)
async def put_upload_content(
    upload_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> None:
    record = db.get(UploadRecord, upload_id)
    if not record:
        raise HTTPException(status_code=404, detail="Upload not found")

    storage = StorageService()
    storage.save_local(record.object_key, file.file)


@router.get("/uploads/{upload_id}")
def get_upload(upload_id: str, db: Session = Depends(get_db)) -> dict:
    record = db.get(UploadRecord, upload_id)
    if not record:
        raise HTTPException(status_code=404, detail="Upload not found")
    return {
        "upload_id": record.id,
        "filename": record.filename,
        "object_key": record.object_key,
        "size_bytes": record.size_bytes,
        "metadata": json.loads(record.sample_json),
        "created_at": record.created_at.isoformat(),
    }
