from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Legacy demo contracts (kept for backward compatibility)
# ---------------------------------------------------------------------------


class AnalyzeResponse(BaseModel):
    status: str
    summary: str
    actions: list[str]
    confidence_score: float = Field(ge=0.0, le=1.0)


class AnalyzeRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    code: str | None = None


LogLevel = Literal["info", "warn", "error", "success"]
LogSessionStatus = Literal["running", "completed", "failed"]


class AgentLogEntry(BaseModel):
    step: int = Field(ge=1)
    message: str
    level: LogLevel = "info"
    timestamp: datetime


class AgentLogHistory(BaseModel):
    session_id: str
    status: LogSessionStatus
    entries: list[AgentLogEntry]


class StreamLogEvent(BaseModel):
    step: int = Field(ge=1)
    message: str
    level: LogLevel = "info"


# ---------------------------------------------------------------------------
# Genomic AST domain contracts
# ---------------------------------------------------------------------------

AnalysisStatus = Literal[
    "queued",
    "uploading",
    "running",
    "completed",
    "failed",
    "cancelled",
]
FileFormat = Literal["fasta", "fastq"]
ReadType = Literal["short", "long", "assembly"]
SusceptibilityLabel = Literal["R", "S", "I", "ATU", "unknown"]
EvidenceSource = Literal["ml", "amrfinderplus", "resfinder", "pointfinder", "reconciled"]


class SampleMetadata(BaseModel):
    sample_name: str = Field(min_length=1, max_length=200)
    organism: str = Field(default="Escherichia coli")
    platform: str | None = None
    read_type: ReadType = "assembly"
    file_format: FileFormat
    notes: str | None = None


class UploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=512)
    content_type: str = "application/octet-stream"
    size_bytes: int = Field(gt=0, le=5_000_000_000)
    metadata: SampleMetadata


class UploadResponse(BaseModel):
    upload_id: str
    upload_url: str
    object_key: str
    expires_in_seconds: int = 3600


class CreateAnalysisRequest(BaseModel):
    upload_id: str
    object_key: str
    metadata: SampleMetadata
    sha256: str | None = None


class CreateAnalysisResponse(BaseModel):
    analysis_id: UUID
    status: AnalysisStatus
    created_at: datetime


class AnalysisStatusResponse(BaseModel):
    analysis_id: UUID
    status: AnalysisStatus
    current_stage: str | None = None
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    created_at: datetime
    updated_at: datetime
    error: str | None = None


class AnalysisEvent(BaseModel):
    sequence: int = Field(ge=1)
    analysis_id: UUID
    stage: str
    message: str
    level: LogLevel = "info"
    timestamp: datetime
    progress: float = Field(default=0.0, ge=0.0, le=1.0)


class QCReport(BaseModel):
    passed: bool
    file_format: FileFormat
    total_bases: int | None = None
    n50: int | None = None
    contig_count: int | None = None
    gc_content: float | None = None
    species_call: str | None = None
    species_confidence: float | None = None
    contamination_flag: bool = False
    notes: list[str] = Field(default_factory=list)


class VariantEvidence(BaseModel):
    gene: str
    mutation: str | None = None
    identity: float | None = None
    coverage: float | None = None
    source: EvidenceSource
    associated_phenotype: SusceptibilityLabel | None = None
    notes: str | None = None


class ShapFeature(BaseModel):
    feature: str
    shap_value: float
    direction: Literal["resistant", "susceptible", "neutral"]
    rank: int = Field(ge=1)


class SusceptibilityCall(BaseModel):
    drug: str = "ciprofloxacin"
    label: SusceptibilityLabel
    probability_resistant: float = Field(ge=0.0, le=1.0)
    calibrated_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    source: EvidenceSource
    breakpoint_standard: str = "EUCAST v16.1"
    confidence: float = Field(ge=0.0, le=1.0)


class AlternativeDrug(BaseModel):
    name: str
    class_name: str
    rationale: str
    caution: str | None = None


class ClinicalInterpretation(BaseModel):
    summary: str
    key_drivers: list[str]
    limitations: list[str]
    alternative_drugs: list[AlternativeDrug]
    disclaimer: str = (
        "Research use only. Not a clinical diagnostic. "
        "Confirm with phenotypic AST before treatment decisions."
    )


class AnalysisResult(BaseModel):
    analysis_id: UUID
    status: AnalysisStatus
    sample: SampleMetadata
    qc: QCReport
    susceptibility: SusceptibilityCall
    variants: list[VariantEvidence]
    shap_features: list[ShapFeature]
    interpretation: ClinicalInterpretation
    pipeline_versions: dict[str, str]
    completed_at: datetime
