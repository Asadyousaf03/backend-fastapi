from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from uuid import UUID

from config import get_settings
from db.models import AnalysisRecord
from db.session import SessionLocal
from schemas import (
    AnalysisProvenance,
    AnalysisResultV2,
    OrganismSelection,
    SampleMetadata,
    SusceptibilityCall,
    VariantEvidence,
)
from services.events import append_event
from services.llm import annotate_antibiogram, interpret_antibiogram
from services.qc import run_qc
from services.reconciliation import reconcile
from services.species import require_species
from services.storage import StorageService
from services.fasta import sanitize_fasta
from services.tools import amrfinderplus, resfinder
from services.tools.versions import TOOL_PINNING


def run_analysis_job(analysis_id: str) -> None:
    settings = get_settings()
    storage = StorageService(settings)
    db = SessionLocal()
    try:
        analysis = db.get(AnalysisRecord, analysis_id)
        if not analysis:
            return

        append_event(
            db,
            analysis_id,
            "queued",
            "Analysis accepted and waiting for compute.",
            progress=0.02,
        )

        if analysis.file_format != "fasta":
            append_event(
                db,
                analysis_id,
                "failed",
                "This release accepts assembled FASTA only.",
                level="error",
                progress=1.0,
            )
            return

        try:
            panel = require_species(analysis.organism)
        except ValueError as exc:
            append_event(
                db,
                analysis_id,
                "failed",
                str(exc),
                level="error",
                progress=1.0,
            )
            return

        organism = OrganismSelection(
            organism_id=panel.organism_id,
            scientific_name=panel.scientific_name,
            requested_name=analysis.organism,
            match_status="selected",
            resfinder_species=panel.resfinder_species,
            amrfinder_organism=panel.amrfinder_organism,
            point_mutations=panel.point_mutations,
            drug_panel=list(panel.drug_panel),
            notes=panel.notes or None,
        )

        append_event(db, analysis_id, "qc", "Validating assembled FASTA.", progress=0.1)
        local_input = storage.ensure_local(analysis.object_key)
        qc = run_qc(local_input, analysis.file_format)  # type: ignore[arg-type]
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

        append_event(
            db,
            analysis_id,
            "species",
            (
                f"Using user-selected organism panel: {panel.scientific_name} "
                f"({len(panel.drug_panel)} drugs)."
            ),
            progress=0.2,
        )

        with tempfile.TemporaryDirectory(prefix=f"ast_{analysis_id}_") as tmp:
            work_dir = Path(tmp)
            assembly_path = work_dir / "assembly.fasta"
            # Normalize contig headers to simple unique ids. Real-world FASTA
            # (BV-BRC/ENA/NCBI) uses headers like ">accn|562.x.con.0444 [..]"
            # whose pipe/bracket characters break AMRFinderPlus' BLAST step.
            sanitize_fasta(local_input, assembly_path)

            append_event(
                db,
                analysis_id,
                "resfinder",
                "Running ResFinder phenotype inference (primary).",
                progress=0.4,
            )
            if settings.tool_execution_mode == "fixture" and settings.allow_fixture_mode:
                rf = resfinder.load_fixture(
                    Path(settings.fixture_dir)
                    / panel.organism_id
                    / "resfinder.json"
                )
            else:
                rf = resfinder.run_resfinder(
                    assembly_path,
                    work_dir,
                    panel,
                    resfinder_db=settings.resfinder_db,
                    pointfinder_db=settings.pointfinder_db,
                    timeout=settings.tool_timeout_seconds,
                )
            if rf.status != "success" and settings.require_real_tools:
                stderr_tail = (rf.tool_run or {}).get("stderr_summary") or ""
                detail = f"ResFinder required but {rf.status}: {rf.error}"
                if stderr_tail:
                    detail += f" | stderr: {stderr_tail[-600:]}"
                append_event(
                    db,
                    analysis_id,
                    "failed",
                    detail,
                    level="error",
                    progress=1.0,
                )
                return

            append_event(
                db,
                analysis_id,
                "amrfinderplus",
                "Running AMRFinderPlus genotypic corroboration.",
                progress=0.6,
            )
            if settings.tool_execution_mode == "fixture" and settings.allow_fixture_mode:
                af = amrfinderplus.load_fixture(
                    Path(settings.fixture_dir)
                    / panel.organism_id
                    / "amrfinder.tsv"
                )
            else:
                af = amrfinderplus.run_amrfinderplus(
                    assembly_path,
                    work_dir,
                    panel,
                    database=settings.amrfinder_db,
                    timeout=settings.tool_timeout_seconds,
                    threads=settings.amrfinder_threads,
                )
            if af.status != "success" and settings.require_real_tools:
                stderr_tail = (af.tool_run or {}).get("stderr_summary") or ""
                detail = f"AMRFinderPlus required but {af.status}: {af.error}"
                if stderr_tail:
                    detail += f" | stderr: {stderr_tail[-600:]}"
                append_event(
                    db,
                    analysis_id,
                    "failed",
                    detail,
                    level="error",
                    progress=1.0,
                )
                return

            # Persist raw artifacts when present.
            artifact_keys: list[str] = []
            if rf.raw_json_path and rf.raw_json_path.exists():
                key = f"results/{analysis_id}/tools/resfinder.json"
                storage.write_bytes(key, rf.raw_json_path.read_bytes())
                artifact_keys.append(key)
                rf.tool_run["artifact_path"] = key
            if af.raw_tsv_path and af.raw_tsv_path.exists():
                key = f"results/{analysis_id}/tools/amrfinder.tsv"
                storage.write_bytes(key, af.raw_tsv_path.read_bytes())
                artifact_keys.append(key)
                af.tool_run["artifact_path"] = key

            append_event(
                db,
                analysis_id,
                "reconcile",
                "Reconciling ResFinder phenotypes with AMRFinderPlus evidence.",
                progress=0.8,
            )
            antibiogram, evidence, tool_runs = reconcile(panel, rf, af)

            append_event(
                db,
                analysis_id,
                "interpretation",
                "Generating research-use-only interpretation summary.",
                progress=0.9,
            )
            antibiogram = annotate_antibiogram(antibiogram, evidence, tool_runs)
            interpretation = interpret_antibiogram(
                organism, antibiogram, evidence, tool_runs
            )

            sample = SampleMetadata(
                sample_name=analysis.sample_name,
                organism=analysis.organism,
                platform=analysis.platform,
                read_type=analysis.read_type,  # type: ignore[arg-type]
                file_format=analysis.file_format,  # type: ignore[arg-type]
                notes=analysis.notes,
            )

            # Legacy single-drug mirror: first ciprofloxacin call if present, else first called.
            legacy_call = next(
                (c for c in antibiogram if c.drug.lower() == "ciprofloxacin" and c.label),
                next((c for c in antibiogram if c.label), None),
            )
            susceptibility = None
            if legacy_call and legacy_call.label:
                susceptibility = SusceptibilityCall(
                    drug=legacy_call.drug,
                    label=legacy_call.label,
                    probability_resistant=1.0 if legacy_call.label == "R" else 0.0,
                    source="reconciled",
                    breakpoint_standard="genotype-inferred (no breakpoint applied)",
                    confidence={"high": 0.85, "moderate": 0.65, "low": 0.4, "none": 0.0}[
                        legacy_call.confidence_category
                    ],
                )

            variants = [
                VariantEvidence(
                    gene=item.gene,
                    mutation=item.mutation,
                    identity=item.identity,
                    coverage=item.coverage,
                    source=item.source,
                    associated_phenotype=item.associated_phenotype,
                    notes=item.notes,
                )
                for item in evidence
            ]

            provenance = AnalysisProvenance(
                schema_version=TOOL_PINNING.result_schema_version,
                pipeline_version=TOOL_PINNING.pipeline_version,
                compute_backend=settings.compute_backend,
                tool_execution_mode=settings.tool_execution_mode,
                notes=[
                    "ResFinder = primary genotype-to-phenotype inference.",
                    "AMRFinderPlus = independent genotypic corroboration (not phenotypic validation).",
                    *([f"artifacts:{','.join(artifact_keys)}"] if artifact_keys else []),
                ],
            )

            result = AnalysisResultV2(
                analysis_id=UUID(analysis_id),
                status="completed",
                sample=sample,
                organism=organism,
                qc=qc,
                antibiogram=antibiogram,
                evidence=evidence,
                tool_runs=tool_runs,
                interpretation=interpretation,
                provenance=provenance,
                completed_at=datetime.utcnow(),
                susceptibility=susceptibility,
                variants=variants,
                shap_features=[],
                pipeline_versions={
                    "api": "2.0.0",
                    "pipeline": TOOL_PINNING.pipeline_version,
                    "schema": TOOL_PINNING.result_schema_version,
                    "resfinder": TOOL_PINNING.resfinder_version,
                    "resfinder_db": TOOL_PINNING.resfinder_db_version,
                    "pointfinder_db": TOOL_PINNING.pointfinder_db_version,
                    "amrfinderplus": TOOL_PINNING.amrfinder_version,
                    "amrfinder_db": TOOL_PINNING.amrfinder_db_version,
                    "compute_backend": settings.compute_backend,
                    "tool_execution_mode": settings.tool_execution_mode,
                },
            )

            analysis.result_json = result.model_dump_json()
            analysis.result_schema_version = "2"
            analysis.status = "completed"
            analysis.progress = 1.0
            analysis.current_stage = "completed"
            analysis.selected_organism_id = panel.organism_id
            analysis.updated_at = datetime.utcnow()
            analysis.error = None
            db.commit()

            storage.write_json(
                f"results/{analysis_id}/result.json",
                json.loads(result.model_dump_json()),
            )
            append_event(
                db,
                analysis_id,
                "completed",
                "Multi-drug genomic antibiogram completed.",
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
