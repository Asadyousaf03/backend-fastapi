from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from schemas import ReadType


def assemble_if_needed(
    input_path: Path,
    work_dir: Path,
    read_type: ReadType,
    file_format: str,
) -> Path:
    """Return an assembly FASTA path. FASTA inputs pass through unchanged."""
    work_dir.mkdir(parents=True, exist_ok=True)
    if file_format == "fasta" or read_type == "assembly":
        out = work_dir / "assembly.fasta"
        if input_path.resolve() != out.resolve():
            shutil.copyfile(input_path, out)
        return out

    if read_type == "long":
        return _run_flye(input_path, work_dir)
    return _run_spades(input_path, work_dir)


def _run_spades(input_path: Path, work_dir: Path) -> Path:
    out_dir = work_dir / "spades"
    out_dir.mkdir(parents=True, exist_ok=True)
    if shutil.which("spades.py"):
        cmd = [
            "spades.py",
            "-s",
            str(input_path),
            "-o",
            str(out_dir),
            "--only-assembler",
            "-t",
            "2",
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        contigs = out_dir / "contigs.fasta"
        if contigs.exists():
            return contigs
    # Demo/local fallback: treat reads as already-usable sequence content.
    fallback = work_dir / "assembly.fasta"
    _fastq_to_pseudo_fasta(input_path, fallback)
    return fallback


def _run_flye(input_path: Path, work_dir: Path) -> Path:
    out_dir = work_dir / "flye"
    out_dir.mkdir(parents=True, exist_ok=True)
    if shutil.which("flye"):
        cmd = [
            "flye",
            "--nano-raw",
            str(input_path),
            "--out-dir",
            str(out_dir),
            "--threads",
            "2",
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        assembly = out_dir / "assembly.fasta"
        if assembly.exists():
            return assembly
    fallback = work_dir / "assembly.fasta"
    _fastq_to_pseudo_fasta(input_path, fallback)
    return fallback


def _fastq_to_pseudo_fasta(input_path: Path, output_path: Path) -> None:
    lines = input_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    sequences: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].startswith("@"):
            if i + 1 < len(lines):
                sequences.append(lines[i + 1].strip().upper())
            i += 4
        else:
            i += 1
    with output_path.open("w", encoding="utf-8") as handle:
        for idx, seq in enumerate(sequences, start=1):
            handle.write(f">contig_{idx}\n{seq}\n")
