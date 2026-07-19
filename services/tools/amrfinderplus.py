"""AMRFinderPlus adapter: independent genotypic corroboration (not phenotype validation)."""

from __future__ import annotations

import csv
import io
import os
from dataclasses import dataclass
from pathlib import Path

from services.species import SpeciesPanel
from services.tools.base import (
    ToolAvailability,
    normalize_fraction,
    run_command,
    slugify,
    which,
)
from services.tools.versions import TOOL_PINNING


@dataclass
class AmrfinderHit:
    evidence_id: str
    gene: str
    mutation: str | None
    identity: float | None
    coverage: float | None
    drug_class: str | None
    subclass: str | None
    method: str | None
    contig: str | None
    start: int | None
    end: int | None
    strand: str | None
    accession: str | None
    scope: str | None
    element_type: str | None
    notes: str | None = None
    source: str = "amrfinderplus"


@dataclass
class AmrfinderResult:
    status: str  # success | failed | unavailable
    hits: list[AmrfinderHit]
    tool_run: dict
    raw_tsv_path: Path | None = None
    error: str | None = None


def build_command(
    fasta_path: Path,
    output_tsv: Path,
    mutation_tsv: Path,
    panel: SpeciesPanel,
    *,
    database: str | None,
    threads: int = 4,
    plus: bool = True,
) -> list[str]:
    exe = which(["amrfinder"]) or "amrfinder"
    cmd = [
        exe,
        "--nucleotide",
        str(fasta_path),
        "--organism",
        panel.amrfinder_organism,
        "--threads",
        str(threads),
        "--output",
        str(output_tsv),
        "--mutation_all",
        str(mutation_tsv),
        "--name",
        panel.organism_id,
    ]
    if plus:
        cmd.append("--plus")
    if database:
        cmd.extend(["--database", database])
    return cmd


def check_availability(*, database: str | None) -> ToolAvailability:
    errors: list[str] = []
    exe = which(["amrfinder"])
    if exe is None:
        errors.append("amrfinder not found on PATH")
    if not which(["blastn"]):
        errors.append("blastn not found on PATH")
    if not which(["hmmsearch"]) and not which(["hmmscan"]):
        errors.append("HMMER (hmmsearch/hmmscan) not found on PATH")
    if not database or not Path(database).exists():
        errors.append(f"AMRFINDER_DB missing: {database}")
    db_version = None
    if database:
        version_file = Path(database) / "version.txt"
        if version_file.exists():
            db_version = version_file.read_text(encoding="utf-8").strip()
    return ToolAvailability(
        ready=not errors,
        tool="amrfinderplus",
        executable=exe,
        version=TOOL_PINNING.amrfinder_version,
        database_path=database,
        database_version=db_version or TOOL_PINNING.amrfinder_db_version,
        errors=errors,
    )


def parse_amrfinder_tsv(text: str) -> list[AmrfinderHit]:
    if not text.strip():
        return []
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    hits: list[AmrfinderHit] = []
    for row in reader:
        gene = (
            row.get("Gene symbol")
            or row.get("gene_symbol")
            or row.get("Element symbol")
            or row.get("Gene")
            or ""
        ).strip()
        if not gene:
            continue
        mutation = (
            row.get("Mutation")
            or row.get("mutation")
            or row.get("Sequence name")
            or None
        )
        if mutation:
            mutation = str(mutation).strip() or None
        identity = _as_float(row.get("% Identity to reference sequence") or row.get("Identity"))
        coverage = _as_float(
            row.get("% Coverage of reference sequence") or row.get("Coverage")
        )
        start = _as_int(row.get("Start") or row.get("start"))
        end = _as_int(row.get("Stop") or row.get("End") or row.get("end"))
        evidence_id = (
            f"amrfinderplus:{slugify(gene)}:"
            f"{slugify(mutation or 'presence')}:"
            f"{start or 0}-{end or 0}"
        )
        hits.append(
            AmrfinderHit(
                evidence_id=evidence_id,
                gene=gene,
                mutation=mutation if mutation and mutation.lower() != gene.lower() else None,
                identity=normalize_fraction(identity),
                coverage=normalize_fraction(coverage),
                drug_class=row.get("Class") or row.get("class"),
                subclass=row.get("Subclass") or row.get("subclass"),
                method=row.get("Method") or row.get("method"),
                contig=row.get("Contig id") or row.get("Contig") or row.get("contig_id"),
                start=start,
                end=end,
                strand=row.get("Strand") or row.get("strand"),
                accession=row.get("Closest reference accession")
                or row.get("Accession of closest sequence"),
                scope=row.get("Scope") or row.get("scope"),
                element_type=row.get("Element type") or row.get("Type"),
                notes=row.get("Element subtype") or row.get("Subtype"),
            )
        )
    return hits


def parse_amrfinder_tsv_file(path: Path) -> list[AmrfinderHit]:
    return parse_amrfinder_tsv(path.read_text(encoding="utf-8", errors="ignore"))


def run_amrfinderplus(
    fasta_path: Path,
    work_dir: Path,
    panel: SpeciesPanel,
    *,
    database: str | None,
    timeout: int,
    threads: int = 4,
) -> AmrfinderResult:
    availability = check_availability(database=database)
    if not availability.ready:
        return AmrfinderResult(
            status="unavailable",
            hits=[],
            tool_run=_tool_run(
                status="unavailable",
                command=[],
                error="; ".join(availability.errors),
                version=availability.version,
                database_version=availability.database_version,
            ),
            error="; ".join(availability.errors),
        )

    out_dir = work_dir / "amrfinderplus"
    out_dir.mkdir(parents=True, exist_ok=True)
    output_tsv = out_dir / "amrfinder.tsv"
    mutation_tsv = out_dir / "mutations.tsv"
    command = build_command(
        fasta_path,
        output_tsv,
        mutation_tsv,
        panel,
        database=database,
        threads=threads,
    )
    result = run_command(command, cwd=out_dir, timeout=timeout, env=os.environ.copy())
    if result.timed_out:
        return AmrfinderResult(
            status="failed",
            hits=[],
            tool_run=_tool_run(
                status="failed",
                command=command,
                error="timeout",
                runtime=result.runtime_seconds,
                stderr=result.stderr,
            ),
            error="AMRFinderPlus timed out",
        )
    if result.exit_code != 0:
        return AmrfinderResult(
            status="failed",
            hits=[],
            tool_run=_tool_run(
                status="failed",
                command=command,
                error=f"exit {result.exit_code}",
                runtime=result.runtime_seconds,
                exit_code=result.exit_code,
                stderr=result.stderr[:4000],
            ),
            error=f"AMRFinderPlus failed with exit code {result.exit_code}",
        )
    if not output_tsv.exists():
        # Some versions write only stdout.
        output_tsv.write_text(result.stdout, encoding="utf-8")
    hits = parse_amrfinder_tsv_file(output_tsv)
    if mutation_tsv.exists():
        hits.extend(parse_amrfinder_tsv_file(mutation_tsv))
    # Deduplicate by evidence_id
    unique: dict[str, AmrfinderHit] = {h.evidence_id: h for h in hits}
    return AmrfinderResult(
        status="success",
        hits=list(unique.values()),
        raw_tsv_path=output_tsv,
        tool_run=_tool_run(
            status="success",
            command=command,
            runtime=result.runtime_seconds,
            exit_code=result.exit_code,
            version=TOOL_PINNING.amrfinder_version,
            database_version=TOOL_PINNING.amrfinder_db_version,
            artifact=str(output_tsv),
        ),
    )


def load_fixture(fixture_path: Path) -> AmrfinderResult:
    hits = parse_amrfinder_tsv_file(fixture_path)
    return AmrfinderResult(
        status="success",
        hits=hits,
        raw_tsv_path=fixture_path,
        tool_run=_tool_run(
            status="success",
            command=["fixture", str(fixture_path)],
            version=TOOL_PINNING.amrfinder_version,
            database_version=TOOL_PINNING.amrfinder_db_version,
            artifact=str(fixture_path),
            notes="fixture_mode",
        ),
    )


def _tool_run(
    *,
    status: str,
    command: list[str],
    error: str | None = None,
    runtime: float | None = None,
    exit_code: int | None = None,
    stderr: str | None = None,
    version: str | None = None,
    database_version: str | None = None,
    artifact: str | None = None,
    notes: str | None = None,
) -> dict:
    return {
        "tool": "amrfinderplus",
        "status": status,
        "version": version or TOOL_PINNING.amrfinder_version,
        "database_version": database_version or TOOL_PINNING.amrfinder_db_version,
        "command": command,
        "runtime_seconds": runtime,
        "exit_code": exit_code,
        "error": error,
        "stderr_summary": stderr,
        "artifact_path": artifact,
        "notes": notes,
        "role": "genotypic_corroboration",
        "disclaimer": (
            "AMRFinderPlus reports genotype evidence only and does not predict "
            "phenotypic susceptibility by itself."
        ),
    }


def _as_float(value: object) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: object) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None
