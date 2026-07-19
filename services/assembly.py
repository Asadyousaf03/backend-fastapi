from __future__ import annotations

from pathlib import Path

from schemas import FileFormat


def assemble_if_needed(
    input_path: Path,
    work_dir: Path,
    read_type: str,
    file_format: FileFormat,
) -> Path:
    """FASTA pass-through only. Pseudo-assembly and FASTQ assembly are disabled."""
    if file_format != "fasta" or read_type != "assembly":
        raise RuntimeError(
            "Read assembly is disabled in this release. Upload an assembled FASTA."
        )
    destination = work_dir / "assembly.fasta"
    destination.write_bytes(input_path.read_bytes())
    return destination
