from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from config import get_settings
from db.models import AnalysisRecord, UploadRecord
from db.session import get_db
from schemas import (
    AnalysisResult,
    AnalysisResultV2,
    AnalysisStatusResponse,
    CreateAnalysisRequest,
    CreateAnalysisResponse,
    ErrorResponse,
)
from services.compute import dispatch_analysis
from services.events import list_events
from services.species import require_species
from services.storage import StorageService

router = APIRouter(prefix="/api/v1", tags=["analyses"])
router_v2 = APIRouter(prefix="/api/v2", tags=["analyses-v2"])


def _create_analysis(
    payload: CreateAnalysisRequest,
    db: Session,
) -> CreateAnalysisResponse:
    upload = db.get(UploadRecord, payload.upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    if upload.object_key != payload.object_key:
        raise HTTPException(status_code=400, detail="object_key does not match upload")
    if json.loads(upload.sample_json) != payload.metadata.model_dump():
        raise HTTPException(status_code=400, detail="Analysis metadata does not match upload")
    if payload.metadata.file_format != "fasta" or payload.metadata.read_type != "assembly":
        raise HTTPException(
            status_code=400,
            detail="This release accepts assembled FASTA only.",
        )
    try:
        panel = require_species(payload.metadata.organism)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    settings = get_settings()
    storage = StorageService(settings)
    if not storage.exists(upload.object_key):
        raise HTTPException(status_code=409, detail="Upload content is not available yet")

    analysis = AnalysisRecord(
        status="queued",
        current_stage="queued",
        progress=0.0,
        sample_name=payload.metadata.sample_name,
        organism=payload.metadata.organism,
        selected_organism_id=panel.organism_id,
        platform=payload.metadata.platform,
        read_type=payload.metadata.read_type,
        file_format=payload.metadata.file_format,
        notes=payload.metadata.notes,
        upload_id=payload.upload_id,
        object_key=payload.object_key,
        sha256=payload.sha256,
        result_schema_version="2",
        attempt=1,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    try:
        remote_id = dispatch_analysis(analysis.id)
        if remote_id:
            analysis.remote_job_id = remote_id
            db.commit()
    except Exception as exc:
        analysis.status = "failed"
        analysis.error = str(exc)
        analysis.current_stage = "failed"
        analysis.progress = 1.0
        analysis.updated_at = datetime.utcnow()
        db.commit()
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return CreateAnalysisResponse(
        analysis_id=UUID(analysis.id),
        status="queued",
        created_at=analysis.created_at,
    )


@router.post(
    "/analyses",
    response_model=CreateAnalysisResponse,
    status_code=202,
    responses={404: {"model": ErrorResponse}},
)
def create_analysis(
    payload: CreateAnalysisRequest,
    db: Session = Depends(get_db),
) -> CreateAnalysisResponse:
    return _create_analysis(payload, db)


@router_v2.post(
    "/analyses",
    response_model=CreateAnalysisResponse,
    status_code=202,
    responses={404: {"model": ErrorResponse}},
)
def create_analysis_v2(
    payload: CreateAnalysisRequest,
    db: Session = Depends(get_db),
) -> CreateAnalysisResponse:
    return _create_analysis(payload, db)


@router.get(
    "/analyses/{analysis_id}",
    response_model=AnalysisStatusResponse,
    responses={404: {"model": ErrorResponse}},
)
@router_v2.get(
    "/analyses/{analysis_id}",
    response_model=AnalysisStatusResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_analysis_status(
    analysis_id: UUID,
    db: Session = Depends(get_db),
) -> AnalysisStatusResponse:
    analysis = db.get(AnalysisRecord, str(analysis_id))
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return AnalysisStatusResponse(
        analysis_id=UUID(analysis.id),
        status=analysis.status,  # type: ignore[arg-type]
        current_stage=analysis.current_stage,
        progress=analysis.progress,
        created_at=analysis.created_at,
        updated_at=analysis.updated_at,
        error=analysis.error,
    )


@router.get(
    "/analyses/{analysis_id}/result",
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def get_analysis_result(
    analysis_id: UUID,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return v2 when available; otherwise parse legacy v1."""
    analysis = db.get(AnalysisRecord, str(analysis_id))
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if analysis.status != "completed" or not analysis.result_json:
        raise HTTPException(status_code=409, detail="Result not ready")
    payload = json.loads(analysis.result_json)
    if payload.get("schema_version") == "2" or "antibiogram" in payload:
        return AnalysisResultV2.model_validate(payload).model_dump(mode="json")
    return AnalysisResult.model_validate(payload).model_dump(mode="json")


@router_v2.get(
    "/analyses/{analysis_id}/result",
    response_model=AnalysisResultV2,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def get_analysis_result_v2(
    analysis_id: UUID,
    db: Session = Depends(get_db),
) -> AnalysisResultV2:
    analysis = db.get(AnalysisRecord, str(analysis_id))
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if analysis.status != "completed" or not analysis.result_json:
        raise HTTPException(status_code=409, detail="Result not ready")
    payload = json.loads(analysis.result_json)
    if payload.get("schema_version") == "2" or "antibiogram" in payload:
        return AnalysisResultV2.model_validate(payload)
    raise HTTPException(
        status_code=409,
        detail="Result is legacy v1; use /api/v1/analyses/{id}/result",
    )


@router.get("/analyses/{analysis_id}/events")
@router_v2.get("/analyses/{analysis_id}/events")
async def stream_analysis_events(
    analysis_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    analysis = db.get(AnalysisRecord, str(analysis_id))
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    last_event_id = request.headers.get("Last-Event-ID")
    after_sequence = int(last_event_id) if last_event_id and last_event_id.isdigit() else 0

    async def event_generator():
        nonlocal after_sequence
        idle_rounds = 0
        while True:
            if await request.is_disconnected():
                break

            events = list_events(db, str(analysis_id), after_sequence=after_sequence)
            if events:
                idle_rounds = 0
                for event in events:
                    after_sequence = event.sequence
                    payload = event.model_dump_json()
                    yield f"id: {event.sequence}\nevent: progress\ndata: {payload}\n\n"
                    if event.stage in {"completed", "failed"}:
                        yield f"event: {event.stage}\ndata: {payload}\n\n"
                        return
            else:
                idle_rounds += 1
                yield ": keepalive\n\n"
                db.refresh(analysis)
                if analysis.status in {"completed", "failed"} and idle_rounds > 2:
                    terminal = {
                        "analysis_id": str(analysis_id),
                        "status": analysis.status,
                        "sequence": after_sequence,
                    }
                    yield f"event: {analysis.status}\ndata: {json.dumps(terminal)}\n\n"
                    return

            await asyncio.sleep(0.75)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
