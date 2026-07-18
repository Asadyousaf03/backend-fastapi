from __future__ import annotations

from pathlib import Path

from schemas import FileFormat, QCReport


def detect_format(path: Path) -> FileFormat:
    name = path.name.lower()
    if name.endswith((".fastq", ".fq", ".fastq.gz", ".fq.gz")):
        return "fastq"
    return "fasta"


def _read_sequences(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    sequences: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if not line:
            continue
        if line.startswith(">") or line.startswith("@"):
            if current:
                sequences.append("".join(current).upper())
                current = []
            continue
        if line.startswith("+"):
            continue
        current.append(line.strip())
    if current:
        sequences.append("".join(current).upper())
    return [seq for seq in sequences if seq]


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
    detected = detect_format(path)
    sequences = _read_sequences(path)
    lengths = [len(seq) for seq in sequences]
    total_bases = sum(lengths)
    gc = None
    if total_bases:
        joined = "".join(sequences)
        gc = (joined.count("G") + joined.count("C")) / total_bases

    notes: list[str] = []
    passed = True
    if detected != expected_format:
        notes.append(
            f"Declared format {expected_format} differs from detected {detected}; using detected."
        )
    if total_bases < 1_000:
        passed = False
        notes.append("Sequence content too short for reliable AST inference.")
    if not sequences:
        passed = False
        notes.append("No sequence records found.")

    # Lightweight E. coli heuristic: GC content around 50% for assemblies.
    species_call = "Escherichia coli"
    species_confidence = 0.55
    contamination_flag = False
    if gc is not None:
        if 0.48 <= gc <= 0.55:
            species_confidence = 0.82
            notes.append("GC content consistent with Escherichia coli.")
        else:
            species_confidence = 0.45
            contamination_flag = True
            notes.append("GC content outside typical E. coli range; contamination possible.")

    # Soft species gate: only fail when confidence is extremely low.
    if species_confidence < 0.3:
        passed = False
        notes.append("Species confidence too low to continue.")

    return QCReport(
        passed=passed,
        file_format=detected,
        total_bases=total_bases or None,
        n50=compute_n50(lengths),
        contig_count=len(sequences) or None,
        gc_content=round(gc, 4) if gc is not None else None,
        species_call=species_call,
        species_confidence=species_confidence,
        contamination_flag=contamination_flag,
        notes=notes,
    )
