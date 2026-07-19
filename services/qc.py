from __future__ import annotations

from collections import Counter
from pathlib import Path

from schemas import FileFormat, QCReport, QcVerdict


# IUPAC nucleotide alphabet (ambiguous codes included). Lowercase is normalized
# upstream; we keep the set uppercase for membership checks.
IUPAC_NUCLEOTIDES = set("ACGTURYSWKMBDHVN-.")

# Typical bacterial genome size envelope used only for sanity warnings.
# We do not assert a species-specific length because the organism is
# user-selected in this release; we flag assemblies that fall well outside
# the common 1.5 Mb - 9 Mb bacterial range.
MIN_BACTERIAL_BASES_WARN = 1_500_000
MIN_BACTERIAL_BASES_FAIL = 100
MAX_BACTERIAL_BASES_WARN = 9_000_000
GC_WARN_LOW = 0.20
GC_WARN_HIGH = 0.70
N_CONTENT_WARN = 0.02
N_CONTENT_FAIL = 0.10


def detect_format(path: Path) -> FileFormat:
    name = path.name.lower()
    if name.endswith((".fastq", ".fq", ".fastq.gz", ".fq.gz")):
        return "fastq"
    return "fasta"


def _read_records(path: Path) -> list[tuple[str, str]]:
    """Return [(header, sequence_uppered), ...] keeping only nucleotide rows."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    records: list[tuple[str, str]] = []
    header: str | None = None
    current: list[str] = []
    for line in text.splitlines():
        if not line:
            continue
        if line.startswith(">"):
            if header is not None:
                records.append((header, "".join(current).upper()))
            header = line[1:].strip()
            current = []
            continue
        if line.startswith("@") or line.startswith("+"):
            continue
        current.append("".join(ch for ch in line.strip().upper() if ch.isalpha() or ch in {"-", "."}))
    if header is not None:
        records.append((header, "".join(current).upper()))
    return [(h, s) for h, s in records if s]


def _read_sequences(path: Path) -> list[str]:
    return [seq for _, seq in _read_records(path)]


def compute_n50(lengths: list[int]) -> int | None:
    if not lengths:
        return None
    ordered = sorted(lengths, reverse=True)
    half = sum(ordered) / 2
    running = 0
    for length in ordered:
        running += length
        if running >= half:
            return length
    return ordered[-1]


def run_qc(path: Path, expected_format: FileFormat) -> QCReport:
    """Assembly QC only. Does not claim taxonomic identification."""
    detected = detect_format(path)
    notes: list[str] = []
    reasons: list[str] = []
    verdict: QcVerdict = "PASS"

    def escalate(level: QcVerdict) -> None:
        nonlocal verdict
        rank = {"PASS": 0, "WARN": 1, "FAIL": 2}
        if rank[level] > rank[verdict]:
            verdict = level

    if expected_format != "fasta" or detected != "fasta":
        escalate("FAIL")
        msg = "This release accepts assembled FASTA only; FASTQ/read inputs are disabled."
        notes.append(msg)
        reasons.append(msg)
        return QCReport(
            passed=False,
            file_format=detected,
            notes=notes,
            verdict=verdict,
            verdict_reasons=reasons,
        )

    records = _read_records(path)
    sequences = [seq for _, seq in records]
    lengths = [len(seq) for seq in sequences]
    total_bases = sum(lengths)
    header_count = len(records)

    gc = None
    n_content = None
    invalid_chars = 0
    char_counts: Counter[str] = Counter()

    if sequences:
        joined = "".join(sequences)
        char_counts.update(joined)
        if total_bases:
            gc = (char_counts.get("G", 0) + char_counts.get("C", 0)) / total_bases
            n_content = char_counts.get("N", 0) / total_bases
        invalid_chars = sum(
            count for ch, count in char_counts.items() if ch not in IUPAC_NUCLEOTIDES
        )

    # --- Hard failures -------------------------------------------------------
    if not sequences:
        escalate("FAIL")
        reasons.append("No FASTA sequence records found (file has no '>' headers with sequence).")
    if total_bases and total_bases < MIN_BACTERIAL_BASES_FAIL:
        escalate("FAIL")
        reasons.append(
            f"Total sequence length ({total_bases:,} bp) is effectively empty; "
            "no usable assembly content."
        )
    if invalid_chars:
        escalate("FAIL")
        reasons.append(
            f"Sequence contains {invalid_chars:,} non-IUPAC nucleotide character(s); "
            "file may be corrupted, protein, or not a nucleotide FASTA."
        )
    if n_content is not None and n_content >= N_CONTENT_FAIL:
        escalate("FAIL")
        reasons.append(
            f"N (ambiguous) base content is {(n_content * 100):.1f}%, "
            f"at or above the {N_CONTENT_FAIL * 100:.0f}% hard-fail threshold."
        )

    # --- Warnings ------------------------------------------------------------
    if total_bases and total_bases < MIN_BACTERIAL_BASES_WARN:
        escalate("WARN")
        reasons.append(
            "Assembly is shorter than a typical bacterial genome; results may be incomplete."
        )
    if total_bases and total_bases > MAX_BACTERIAL_BASES_WARN:
        escalate("WARN")
        reasons.append(
            "Assembly is larger than a typical single bacterial genome; "
            "verify it is not a concatenation of multiple isolates."
        )
    if gc is not None and (gc < GC_WARN_LOW or gc > GC_WARN_HIGH):
        escalate("WARN")
        reasons.append(
            f"Observed GC content {(gc * 100):.1f}% is outside the usual 20-70% bacterial range."
        )
    if n_content is not None and N_CONTENT_WARN <= n_content < N_CONTENT_FAIL:
        escalate("WARN")
        reasons.append(
            f"Elevated N content ({(n_content * 100):.2f}%); assembly may be fragmented or low-quality."
        )
    if header_count and header_count > 50_000:
        escalate("WARN")
        reasons.append("Very high contig count; assembly may be overly fragmented.")
    if lengths and max(lengths) < 1_000:
        escalate("WARN")
        reasons.append("Longest contig is under 1 kb; assembly quality is marginal for AST inference.")

    # --- Human-readable notes (kept for legacy clients) ---------------------
    notes.append(f"Detected {header_count} FASTA record(s) totaling {total_bases:,} bp.")
    if gc is not None:
        notes.append(f"Observed GC content={(gc * 100):.1f}%.")
    if n_content is not None:
        notes.append(f"N (ambiguous) base content={(n_content * 100):.2f}%.")
    if invalid_chars:
        notes.append(f"Non-IUPAC nucleotide characters observed: {invalid_chars}.")
    notes.append(
        "Species is user-selected for this release; QC does not perform taxonomic identification."
    )

    passed = verdict != "FAIL"
    return QCReport(
        passed=passed,
        file_format=detected,
        total_bases=total_bases or None,
        n50=compute_n50(lengths),
        contig_count=header_count or None,
        gc_content=round(gc, 4) if gc is not None else None,
        species_call=None,
        species_confidence=None,
        contamination_flag=False,
        notes=notes,
        verdict=verdict,
        verdict_reasons=reasons,
        header_count=header_count or None,
        invalid_chars=invalid_chars or None,
        n_content=round(n_content, 4) if n_content is not None else None,
        min_contig_length=min(lengths) if lengths else None,
        max_contig_length=max(lengths) if lengths else None,
    )
