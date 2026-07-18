from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from schemas import SusceptibilityLabel, VariantEvidence


KNOWN_CIPRO_MARKERS = {
    "gyrA_S83L": ("gyrA", "S83L"),
    "gyrA_D87N": ("gyrA", "D87N"),
    "parC_S80I": ("parC", "S80I"),
    "qnrS": ("qnrS", None),
    "aac(6')-Ib-cr": ("aac(6')-Ib-cr", None),
}


def _scan_sequence_for_markers(sequence: str) -> list[VariantEvidence]:
    """Heuristic marker scan used when external tools are unavailable.

    Looks for short signature motifs associated with fluoroquinolone resistance
    literature markers. This is a research demo corroborator, not a replacement
    for AMRFinderPlus / PointFinder in production.
    """
    evidence: list[VariantEvidence] = []
    motifs = {
        "gyrA": "GCGCGTACTTTACGCCGAT",
        "parC": "ATGAGCGATATGGCAGAG",
        "qnrS": "ATGGAAACCTACAATCATAC",
        "aac(6')-Ib-cr": "ATGAGCAACGCAAAAACAAAGTTA",
    }
    for gene, motif in motifs.items():
        if motif in sequence:
            mutation = None
            if gene == "gyrA":
                mutation = "S83L"
            elif gene == "parC":
                mutation = "S80I"
            evidence.append(
                VariantEvidence(
                    gene=gene,
                    mutation=mutation,
                    identity=0.98,
                    coverage=1.0,
                    source="pointfinder" if mutation else "resfinder",
                    associated_phenotype="R",
                    notes="Detected via local marker scan (demo fallback).",
                )
            )
    return evidence


def _run_amrfinderplus(assembly_path: Path) -> list[VariantEvidence]:
    if not shutil.which("amrfinder"):
        return []
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "amr.tsv"
        cmd = [
            "amrfinder",
            "-n",
            str(assembly_path),
            "-O",
            "Escherichia",
            "-o",
            str(out),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError:
            return []
        return _parse_amrfinder_tsv(out)


def _parse_amrfinder_tsv(path: Path) -> list[VariantEvidence]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    if len(lines) < 2:
        return []
    header = lines[0].split("\t")
    evidence: list[VariantEvidence] = []
    for line in lines[1:]:
        cols = dict(zip(header, line.split("\t"), strict=False))
        gene = cols.get("Gene symbol") or cols.get("Element symbol") or ""
        subtype = cols.get("Element subtype") or ""
        name = cols.get("Element name") or ""
        relevant = any(
            token.lower() in f"{gene} {name} {subtype}".lower()
            for token in ("gyra", "parc", "qnrs", "aac(6')-ib-cr", "fluoroquinolone")
        )
        if not relevant:
            continue
        mutation = None
        match = re.search(r"([A-Z]\d+[A-Z])", name)
        if match:
            mutation = match.group(1)
        evidence.append(
            VariantEvidence(
                gene=gene or name,
                mutation=mutation,
                identity=float(cols["% Identity to reference sequence"])
                if cols.get("% Identity to reference sequence")
                else None,
                coverage=float(cols["% Coverage of reference sequence"])
                if cols.get("% Coverage of reference sequence")
                else None,
                source="amrfinderplus",
                associated_phenotype="R",
                notes=subtype or None,
            )
        )
    return evidence


def detect_cipro_markers(assembly_path: Path) -> list[VariantEvidence]:
    sequence = "".join(
        line.strip().upper()
        for line in assembly_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if not line.startswith(">")
    )
    tool_hits = _run_amrfinderplus(assembly_path)
    if tool_hits:
        return tool_hits
    return _scan_sequence_for_markers(sequence)


def rule_based_call(variants: list[VariantEvidence]) -> SusceptibilityLabel:
    if any(v.associated_phenotype == "R" for v in variants):
        return "R"
    return "S"
