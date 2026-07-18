from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from config import get_settings
from db.models import AnalysisRecord
from db.session import SessionLocal
from schemas import AnalysisResult, SampleMetadata
from services.assembly import assemble_if_needed
from services.events import append_event
from services.llm import interpret_clinically
from services.ml_core import predict_ciprofloxacin
from services.qc import run_qc
from services.rules import detect_cipro_markers
from services.storage import StorageService


PIPELINE_VERSIONS = {
    "api": "1.0.0",
    "pipeline": "genomic-ast-mvp-1",
    "amrpredictor": "zenodo-16213507",
    "amrfinderplus": "optional-local-or-fallback",
    "resfinder_pointfinder": "optional-local-or-fallback",
    "breakpoint": "EUCAST v16.1",
}


def run_analysis_job(analysis_id: str) -> None:
    settings = get_settings()
    storage = StorageService(settings)
    db = SessionLocal()
    try:
        analysis = db.get(AnalysisRecord, analysis_id)
        if not analysis:
            return

        append_event(db, analysis_id, "queued", "Analysis accepted and waiting for compute.", progress=0.02)
        append_event(db, analysis_id, "qc", "Validating uploaded genomic file.", progress=0.1)

        input_path = storage.resolve_path(analysis.object_key)
        qc = run_qc(input_path, analysis.file_format)  # type: ignore[arg-type]
        if not qc.passed:
            append_event(
                db,
                analysis_id,
                "failed",
                "QC failed: " + "; ".join(qc.notes) if qc.notes else "QC failed.",
                level="error",
                progress=1.0,
            )
            return

        append_event(db, analysis_id, "assembly", "Preparing clean assembly sequence.", progress=0.3)
        with tempfile.TemporaryDirectory(prefix=f"ast_{analysis_id}_") as tmp:
            work_dir = Path(tmp)
            assembly_path = assemble_if_needed(
                input_path,
                work_dir,
                analysis.read_type,  # type: ignore[arg-type]
                qc.file_format,
            )

            append_event(
                db,
                analysis_id,
                "species",
                f"Species check: {qc.species_call} (confidence={qc.species_confidence}).",
                progress=0.4,
                level="warn" if qc.contamination_flag else "info",
            )
            if (qc.species_confidence or 0) < 0.3:
                append_event(
                    db,
                    analysis_id,
                    "failed",
                    "Species/contamination gate failed for non-confident E. coli call.",
                    level="error",
                    progress=1.0,
                )
                return

            append_event(
                db,
                analysis_id,
                "features",
                "Extracting k-mer features and scanning ciprofloxacin markers.",
                progress=0.55,
            )
            variants = detect_cipro_markers(assembly_path)

            append_event(
                db,
                analysis_id,
                "ml",
                "Running AMRpredictor XGBoost inference and SHAP explanations.",
                progress=0.7,
            )
            ml = predict_ciprofloxacin(assembly_path, variants)

            append_event(
                db,
                analysis_id,
                "rules",
                "Reconciling ML call with ResFinder/AMRFinderPlus-style evidence.",
                progress=0.82,
            )

            append_event(
                db,
                analysis_id,
                "interpretation",
                "Generating research-use-only clinical interpretation.",
                progress=0.9,
            )
            interpretation = interpret_clinically(ml.call, variants, ml.shap_features)

            sample = SampleMetadata(
                sample_name=analysis.sample_name,
                organism=analysis.organism,
                platform=analysis.platform,
                read_type=analysis.read_type,  # type: ignore[arg-type]
                file_format=analysis.file_format,  # type: ignore[arg-type]
                notes=analysis.notes,
            )
            result = AnalysisResult(
                analysis_id=UUID(analysis_id),
                status="completed",
                sample=sample,
                qc=qc,
                susceptibility=ml.call,
                variants=variants,
                shap_features=ml.shap_features,
                interpretation=interpretation,
                pipeline_versions={
                    **PIPELINE_VERSIONS,
                    "pretrained_weights_loaded": str(ml.used_pretrained).lower(),
                    "compute_backend": settings.compute_backend,
                },
                completed_at=datetime.utcnow(),
            )

            analysis.result_json = result.model_dump_json()
            analysis.status = "completed"
            analysis.progress = 1.0
            analysis.current_stage = "completed"
            analysis.updated_at = datetime.utcnow()
            db.commit()

            storage.write_json(
                f"results/{analysis_id}/result.json",
                json.loads(result.model_dump_json()),
            )
            append_event(
                db,
                analysis_id,
                "completed",
                "Workflow execution successfully finished.",
                level="success",
                progress=1.0,
            )
    except Exception as exc:
        append_event(
            db,
            analysis_id,
            "failed",
            f"Pipeline error: {exc}",
            level="error",
            progress=1.0,
        )
    finally:
        db.close()
