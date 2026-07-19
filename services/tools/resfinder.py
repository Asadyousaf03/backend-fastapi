"""ResFinder 4.x adapter: primary genotype-to-phenotype inference."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from services.species import SpeciesPanel
from services.tools.base import (
    SubprocessResult,
    ToolAvailability,
    ToolExecutionError,
    normalize_fraction,
    run_command,
    slugify,
    which,
)
from services.tools.versions import TOOL_PINNING


@dataclass
class ResFinderHit:
    evidence_id: str
    gene: str
    mutation: str | None
    identity: float | None
    coverage: float | None
    phenotype_drugs: list[str]
    phenotype_label: str | None
    contig: str | None = None
    start: int | None = None
    end: int | None = None
    accession: str | None = None
    notes: str | None = None
    source: str = "resfinder"


@dataclass
class ResFinderPhenotype:
    drug: str
    drug_class: str | None
    label: str | None
    genes: list[str] = field(default_factory=list)


@dataclass
class ResFinderResult:
    status: str  # success | failed | unavailable
    phenotypes: list[ResFinderPhenotype]
    hits: list[ResFinderHit]
    tool_run: dict
    raw_json_path: Path | None = None
    error: str | None = None


def build_command(
    fasta_path: Path,
    output_dir: Path,
    panel: SpeciesPanel,
    *,
    resfinder_db: str,
    pointfinder_db: str,
    acquired: bool = True,
    point: bool = True,
) -> list[str]:
    python = which(["python3", "python"]) or "python"
    cmd = [
        python,
        "-m",
        "resfinder",
        "-ifa",
        str(fasta_path),
        "-o",
        str(output_dir),
        "-s",
        panel.resfinder_species,
        "--db_path_res",
        resfinder_db,
        "-j",
        str(output_dir / "resfinder.json"),
    ]
    if acquired:
        cmd.append("--acquired")
    if point and panel.point_mutations:
        cmd.extend(["--point", "--db_path_point", pointfinder_db])
    return cmd


def check_availability(
    *,
    resfinder_db: str | None,
    pointfinder_db: str | None,
) -> ToolAvailability:
    errors: list[str] = []
    exe = which(["resfinder"]) or which(["python3", "python"])
    if which(["resfinder"]) is None:
        # Module form is acceptable.
        try:
            import importlib.util

            if importlib.util.find_spec("resfinder") is None:
                errors.append("resfinder Python package not installed")
        except Exception:
            errors.append("unable to inspect resfinder package")
    if not which(["blastn"]):
        errors.append("blastn not found on PATH")
    if not resfinder_db or not Path(resfinder_db).exists():
        errors.append(f"RESFINDER_DB missing: {resfinder_db}")
    if not pointfinder_db or not Path(pointfinder_db).exists():
        errors.append(f"POINTFINDER_DB missing: {pointfinder_db}")
    version = TOOL_PINNING.resfinder_version
    db_version = None
    if resfinder_db and Path(resfinder_db, "VERSION").exists():
        db_version = Path(resfinder_db, "VERSION").read_text(encoding="utf-8").strip()
    return ToolAvailability(
        ready=not errors,
        tool="resfinder",
        executable=exe,
        version=version,
        database_path=resfinder_db,
        database_version=db_version,
        errors=errors,
    )


def parse_resfinder_json(payload: dict) -> tuple[list[ResFinderPhenotype], list[ResFinderHit]]:
    phenotypes: list[ResFinderPhenotype] = []
    hits: list[ResFinderHit] = []

    # Phenotype tables vary by ResFinder version; support common shapes.
    pheno = payload.get("phenotypes") or payload.get("phenotype") or {}
    if isinstance(pheno, dict):
        for drug, info in pheno.items():
            if not isinstance(info, dict):
                continue
            resistant = info.get("resistant") or info.get("Resistance") or info.get("res")
            label = None
            if resistant in (True, "1", 1, "R", "Resistant", "resistant"):
                label = "R"
            elif resistant in (False, "0", 0, "S", "Sensitive", "susceptible", "Susceptible"):
                label = "S"
            genes = info.get("genes") or info.get("Genes") or []
            if isinstance(genes, str):
                genes = [genes]
            phenotypes.append(
                ResFinderPhenotype(
                    drug=str(drug),
                    drug_class=info.get("class") or info.get("Class"),
                    label=label,
                    genes=[str(g) for g in genes],
                )
            )

    seq_results = payload.get("seq_region") or payload.get("resfinder") or {}
    if isinstance(seq_results, dict):
        for key, region in seq_results.items():
            if not isinstance(region, dict):
                continue
            gene = str(region.get("name") or region.get("gene") or key)
            identity = _as_float(region.get("identity") or region.get("Identity"))
            coverage = _as_float(
                region.get("coverage")
                or region.get("Coverage")
                or region.get("query_coverage")
            )
            drugs = region.get("phenotypes") or region.get("phenotype") or []
            if isinstance(drugs, str):
                drugs = [drugs]
            mutation = region.get("ref_id") if ":" in str(region.get("ref_id", "")) else None
            if region.get("mutation"):
                mutation = str(region.get("mutation"))
            evidence_id = f"resfinder:{slugify(gene)}:{slugify(str(mutation or 'presence'))}"
            hits.append(
                ResFinderHit(
                    evidence_id=evidence_id,
                    gene=gene,
                    mutation=str(mutation) if mutation else None,
                    identity=normalize_fraction(identity),
                    coverage=normalize_fraction(coverage),
                    phenotype_drugs=[str(d) for d in drugs],
                    phenotype_label="R" if drugs else None,
                    contig=region.get("contig") or region.get("query_id"),
                    start=_as_int(region.get("start") or region.get("query_start")),
                    end=_as_int(region.get("end") or region.get("query_end")),
                    accession=region.get("ref_acc") or region.get("accession"),
                    notes="acquired_gene",
                    source="resfinder",
                )
            )

    point = payload.get("pointfinder") or payload.get("seq_variations") or {}
    if isinstance(point, dict):
        for key, region in point.items():
            if not isinstance(region, dict):
                continue
            gene = str(region.get("gene") or region.get("name") or key)
            mutation = str(
                region.get("mutation")
                or region.get("aa")
                or region.get("nuc")
                or "mutation"
            )
            drugs = region.get("phenotypes") or region.get("phenotype") or []
            if isinstance(drugs, str):
                drugs = [drugs]
            evidence_id = f"pointfinder:{slugify(gene)}:{slugify(mutation)}"
            hits.append(
                ResFinderHit(
                    evidence_id=evidence_id,
                    gene=gene,
                    mutation=mutation,
                    identity=normalize_fraction(_as_float(region.get("identity"))),
                    coverage=normalize_fraction(_as_float(region.get("coverage"))),
                    phenotype_drugs=[str(d) for d in drugs],
                    phenotype_label="R",
                    contig=region.get("contig"),
                    start=_as_int(region.get("start")),
                    end=_as_int(region.get("end")),
                    accession=region.get("ref_acc"),
                    notes="point_mutation",
                    source="pointfinder",
                )
            )

    # Fallback: parse pheno_table style nested lists if present.
    for table_key in ("pheno_table_species", "pheno_table"):
        table = payload.get(table_key)
        if isinstance(table, list):
            for row in table:
                if not isinstance(row, dict):
                    continue
                drug = row.get("Antimicrobial") or row.get("antimicrobial") or row.get("drug")
                if not drug:
                    continue
                match = str(row.get("Match") or row.get("match") or "").lower()
                label = "R" if match in {"1", "true", "yes", "resistant", "r"} else None
                if match in {"0", "false", "no", "sensitive", "s", "susceptible"}:
                    label = "S"
                phenotypes.append(
                    ResFinderPhenotype(
                        drug=str(drug),
                        drug_class=row.get("Class") or row.get("class"),
                        label=label,
                        genes=[],
                    )
                )

    return _dedupe_phenotypes(phenotypes), hits


def parse_resfinder_json_file(path: Path) -> tuple[list[ResFinderPhenotype], list[ResFinderHit]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return parse_resfinder_json(payload)


def run_resfinder(
    fasta_path: Path,
    work_dir: Path,
    panel: SpeciesPanel,
    *,
    resfinder_db: str,
    pointfinder_db: str,
    timeout: int,
) -> ResFinderResult:
    availability = check_availability(
        resfinder_db=resfinder_db,
        pointfinder_db=pointfinder_db,
    )
    if not availability.ready:
        return ResFinderResult(
            status="unavailable",
            phenotypes=[],
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

    out_dir = work_dir / "resfinder"
    out_dir.mkdir(parents=True, exist_ok=True)
    command = build_command(
        fasta_path,
        out_dir,
        panel,
        resfinder_db=resfinder_db,
        pointfinder_db=pointfinder_db,
    )
    env = os.environ.copy()
    result = run_command(command, cwd=out_dir, timeout=timeout, env=env)
    if result.timed_out:
        return ResFinderResult(
            status="failed",
            phenotypes=[],
            hits=[],
            tool_run=_tool_run(
                status="failed",
                command=command,
                error="timeout",
                runtime=result.runtime_seconds,
                exit_code=None,
                stderr=result.stderr,
            ),
            error="ResFinder timed out",
        )
    if result.exit_code != 0:
        return ResFinderResult(
            status="failed",
            phenotypes=[],
            hits=[],
            tool_run=_tool_run(
                status="failed",
                command=command,
                error=f"exit {result.exit_code}",
                runtime=result.runtime_seconds,
                exit_code=result.exit_code,
                stderr=result.stderr[:4000],
            ),
            error=f"ResFinder failed with exit code {result.exit_code}",
        )

    json_path = out_dir / "resfinder.json"
    if not json_path.exists():
        # Some versions write data.json
        candidates = list(out_dir.glob("*.json"))
        json_path = candidates[0] if candidates else json_path
    if not json_path.exists():
        return ResFinderResult(
            status="failed",
            phenotypes=[],
            hits=[],
            tool_run=_tool_run(
                status="failed",
                command=command,
                error="missing JSON output",
                runtime=result.runtime_seconds,
                exit_code=result.exit_code,
                stderr=result.stderr[:4000],
            ),
            error="ResFinder produced no JSON output",
        )

    phenotypes, hits = parse_resfinder_json_file(json_path)
    return ResFinderResult(
        status="success",
        phenotypes=phenotypes,
        hits=hits,
        raw_json_path=json_path,
        tool_run=_tool_run(
            status="success",
            command=command,
            runtime=result.runtime_seconds,
            exit_code=result.exit_code,
            version=TOOL_PINNING.resfinder_version,
            database_version=TOOL_PINNING.resfinder_db_version,
            database_commit=TOOL_PINNING.resfinder_db_commit,
            artifact=str(json_path),
        ),
    )


def load_fixture(fixture_path: Path) -> ResFinderResult:
    phenotypes, hits = parse_resfinder_json_file(fixture_path)
    return ResFinderResult(
        status="success",
        phenotypes=phenotypes,
        hits=hits,
        raw_json_path=fixture_path,
        tool_run=_tool_run(
            status="success",
            command=["fixture", str(fixture_path)],
            version=TOOL_PINNING.resfinder_version,
            database_version=TOOL_PINNING.resfinder_db_version,
            database_commit=TOOL_PINNING.resfinder_db_commit,
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
    database_commit: str | None = None,
    artifact: str | None = None,
    notes: str | None = None,
) -> dict:
    return {
        "tool": "resfinder",
        "status": status,
        "version": version or TOOL_PINNING.resfinder_version,
        "database_version": database_version,
        "database_commit": database_commit or TOOL_PINNING.resfinder_db_commit,
        "command": command,
        "runtime_seconds": runtime,
        "exit_code": exit_code,
        "error": error,
        "stderr_summary": stderr,
        "artifact_path": artifact,
        "notes": notes,
        "role": "primary_inference",
    }


def _dedupe_phenotypes(items: list[ResFinderPhenotype]) -> list[ResFinderPhenotype]:
    by_drug: dict[str, ResFinderPhenotype] = {}
    for item in items:
        key = item.drug.strip().lower()
        existing = by_drug.get(key)
        if existing is None:
            by_drug[key] = item
            continue
        if existing.label is None and item.label is not None:
            by_drug[key] = item
        elif item.label == "R":
            by_drug[key] = item
        genes = list(dict.fromkeys([*existing.genes, *item.genes]))
        by_drug[key] = ResFinderPhenotype(
            drug=by_drug[key].drug,
            drug_class=by_drug[key].drug_class or item.drug_class,
            label=by_drug[key].label,
            genes=genes,
        )
    return list(by_drug.values())


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
        return int(value)
    except (TypeError, ValueError):
        return None
