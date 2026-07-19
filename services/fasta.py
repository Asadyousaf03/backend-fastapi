"""FASTA normalization utilities.

Uploaded assemblies (e.g. from BV-BRC, ENA, NCBI) frequently carry contig
headers such as ``>accn|562.56783.con.0444   undefined   [undefined | 562...]``.
The pipe/bracket characters trip AMRFinderPlus' BLAST step (makeblastdb parses
``accn|...`` as an NCBI-style seqid and rejects malformed or duplicate ids),
which surfaces as exit code 1. Renaming every contig to a simple unique token
before running the tools makes the pipeline robust to arbitrary real-world
FASTA headers without changing the underlying sequence.
"""

from __future__ import annotations

from pathlib import Path


def sanitize_fasta(src: Path, dst: Path) -> dict[str, str]:
    """Copy ``src`` to ``dst`` with simple unique contig ids.

    Returns a mapping of ``new_id -> original_header`` so downstream code can
    trace a hit back to the uploaded contig name if needed.
    """
    mapping: dict[str, str] = {}
    index = 0
    with (
        src.open("r", encoding="utf-8", errors="ignore") as handle,
        dst.open("w", encoding="utf-8", newline="\n") as out,
    ):
        for line in handle:
            if line.startswith(">"):
                index += 1
                original = line[1:].strip()
                new_id = f"contig{index}"
                mapping[new_id] = original
                out.write(f">{new_id}\n")
            else:
                seq = line.strip()
                if seq:
                    out.write(seq + "\n")
    return mapping
