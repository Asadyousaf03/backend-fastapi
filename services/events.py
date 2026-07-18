from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models import AnalysisEventRecord, AnalysisRecord
from schemas import AnalysisEvent, LogLevel


def append_event(
    db: Session,
    analysis_id: str,
    stage: str,
    message: str,
    *,
    level: LogLevel = "info",
    progress: float = 0.0,
) -> AnalysisEvent:
    next_seq = db.scalar(
        select(func.coalesce(func.max(AnalysisEventRecord.sequence), 0)).where(
            AnalysisEventRecord.analysis_id == analysis_id
        )
    )
    sequence = int(next_seq or 0) + 1
    record = AnalysisEventRecord(
        analysis_id=analysis_id,
        sequence=sequence,
        stage=stage,
        message=message,
        level=level,
        progress=progress,
        timestamp=datetime.utcnow(),
    )
    db.add(record)

    analysis = db.get(AnalysisRecord, analysis_id)
    if analysis:
        analysis.current_stage = stage
        analysis.progress = progress
        analysis.updated_at = datetime.utcnow()
        if stage == "failed":
            analysis.status = "failed"
            analysis.error = message
        elif stage == "completed":
            analysis.status = "completed"
        elif analysis.status in {"queued", "uploading"}:
            analysis.status = "running"

    db.commit()
    db.refresh(record)
    return AnalysisEvent(
        sequence=record.sequence,
        analysis_id=UUID(analysis_id),
        stage=record.stage,
        message=record.message,
        level=record.level,  # type: ignore[arg-type]
        timestamp=record.timestamp,
        progress=record.progress,
    )


def list_events(
    db: Session,
    analysis_id: str,
    after_sequence: int = 0,
) -> list[AnalysisEvent]:
    rows = db.scalars(
        select(AnalysisEventRecord)
        .where(
            AnalysisEventRecord.analysis_id == analysis_id,
            AnalysisEventRecord.sequence > after_sequence,
        )
        .order_by(AnalysisEventRecord.sequence.asc())
    ).all()
    return [
        AnalysisEvent(
            sequence=row.sequence,
            analysis_id=UUID(analysis_id),
            stage=row.stage,
            message=row.message,
            level=row.level,  # type: ignore[arg-type]
            timestamp=row.timestamp,
            progress=row.progress,
        )
        for row in rows
    ]
