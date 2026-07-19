from datetime import datetime
from typing import Any, Literal
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
EvidenceSource = Literal[
    "ml",
    "heuristic",
    "amrfinderplus",
    "resfinder",
    "pointfinder",
    "reconciled",
]
CallStatus = Literal[
    "called",
    "unknown",
    "unsupported",
    "conflicting",
    "insufficient_evidence",
    "tool_failed",
]
EvidenceAgreement = Literal[
    "concordant",
    "complementary",
    "discordant",
    "single_source",
    "no_resistance_evidence",
    "not_assessed",
    "tool_failure",
]
ToolRunStatus = Literal["success", "failed", "unavailable", "skipped"]
OrganismMatchStatus = Literal[
    "selected",
    "unsupported",
    "missing",
]


class SampleMetadata(BaseModel):
    sample_name: str = Field(min_length=1, max_length=200)
    organism: str = Field(
        ...,
        description="Expected organism scientific name or organism_id from capabilities.",
    )
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


QcVerdict = Literal["PASS", "WARN", "FAIL"]


class InterpretationReference(BaseModel):
    """Citable source backing a resistance call or interpretation."""

    source: str
    version: str | None = None
    database_version: str | None = None
    database_commit: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    url: str | None = None
    role: str | None = None


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
    # Structured FASTA usability verdict (additive, backward compatible).
    verdict: QcVerdict | None = None
    verdict_reasons: list[str] = Field(default_factory=list)
    header_count: int | None = None
    invalid_chars: int | None = None
    n_content: float | None = Field(default=None, ge=0.0, le=1.0)
    min_contig_length: int | None = None
    max_contig_length: int | None = None


class VariantEvidence(BaseModel):
    """Legacy v1 evidence item retained for migrated results."""

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
    alternative_drugs: list[AlternativeDrug] = Field(default_factory=list)
    disclaimer: str = (
        "Research use only. Not a clinical diagnostic. "
        "Confirm with phenotypic AST before treatment decisions."
    )
    # Dual-audience summaries (additive, backward compatible).
    clinician_summary: str | None = None
    layperson_summary: str | None = None
    references: list[InterpretationReference] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    """Legacy v1 single-drug result."""

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


# ---------------------------------------------------------------------------
# V2 multi-pathogen antibiogram contracts
# ---------------------------------------------------------------------------


class OrganismSelection(BaseModel):
    organism_id: str
    scientific_name: str
    requested_name: str
    match_status: OrganismMatchStatus = "selected"
    resfinder_species: str
    amrfinder_organism: str
    point_mutations: bool = True
    drug_panel: list[str] = Field(default_factory=list)
    notes: str | None = None


class ResistanceEvidence(BaseModel):
    evidence_id: str
    gene: str
    mutation: str | None = None
    identity: float | None = Field(default=None, ge=0.0, le=1.0)
    coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    source: EvidenceSource
    associated_drugs: list[str] = Field(default_factory=list)
    drug_class: str | None = None
    subclass: str | None = None
    method: str | None = None
    contig: str | None = None
    start: int | None = None
    end: int | None = None
    strand: str | None = None
    accession: str | None = None
    associated_phenotype: SusceptibilityLabel | None = None
    notes: str | None = None


class ToolRun(BaseModel):
    tool: str
    status: ToolRunStatus
    role: str
    version: str | None = None
    database_version: str | None = None
    database_commit: str | None = None
    command: list[str] = Field(default_factory=list)
    runtime_seconds: float | None = None
    exit_code: int | None = None
    error: str | None = None
    stderr_summary: str | None = None
    artifact_path: str | None = None
    notes: str | None = None
    disclaimer: str | None = None


class SourceAssessment(BaseModel):
    source: EvidenceSource
    status: Literal[
        "resistance_evidence",
        "no_reportable_evidence",
        "not_assessed",
        "tool_unavailable",
        "tool_failed",
    ]
    label: SusceptibilityLabel | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    notes: str | None = None


class AntimicrobialCall(BaseModel):
    drug_id: str
    drug: str
    drug_class: str | None = None
    label: SusceptibilityLabel | None = None
    call_status: CallStatus
    agreement: EvidenceAgreement
    evidence_ids: list[str] = Field(default_factory=list)
    source_assessments: list[SourceAssessment] = Field(default_factory=list)
    confidence_category: Literal["high", "moderate", "low", "none"] = "none"
    breakpoint_standard: str | None = None
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    # Dual-audience rationale + traceable references (additive, backward compatible).
    clinician_rationale: str | None = None
    layperson_rationale: str | None = None
    references: list[InterpretationReference] = Field(default_factory=list)


class AnalysisProvenance(BaseModel):
    schema_version: str = "2"
    pipeline_version: str
    compute_backend: str
    image_digest: str | None = None
    tool_execution_mode: str
    notes: list[str] = Field(default_factory=list)


class AnalysisResultV2(BaseModel):
    schema_version: Literal["2"] = "2"
    analysis_id: UUID
    status: AnalysisStatus
    sample: SampleMetadata
    organism: OrganismSelection
    qc: QCReport
    antibiogram: list[AntimicrobialCall]
    evidence: list[ResistanceEvidence]
    tool_runs: list[ToolRun]
    interpretation: ClinicalInterpretation
    provenance: AnalysisProvenance
    completed_at: datetime
    # Optional legacy mirrors for transitional clients
    susceptibility: SusceptibilityCall | None = None
    variants: list[VariantEvidence] = Field(default_factory=list)
    shap_features: list[ShapFeature] = Field(default_factory=list)
    pipeline_versions: dict[str, str] = Field(default_factory=dict)


class SpeciesCapability(BaseModel):
    organism_id: str
    scientific_name: str
    aliases: list[str]
    resfinder_species: str
    amrfinder_organism: str
    point_mutations: bool
    drug_panel: list[str]
    notes: str = ""


class ApiCapabilitiesV2(BaseModel):
    schema_version: str = "2"
    mode: Literal["tools-required", "fixture"]
    supported_file_formats: list[FileFormat]
    max_upload_bytes: int
    compute_backend: str
    storage_backend: str
    require_real_tools: bool
    tools_ready: bool
    species: list[SpeciesCapability]
    pinned: dict[str, str]
    notes: list[str] = Field(default_factory=list)
    readiness: dict[str, Any] = Field(default_factory=dict)
