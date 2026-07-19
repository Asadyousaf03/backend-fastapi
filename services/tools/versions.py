"""Pinned scientific runtime versions for reproducible genomic AST."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolPinning:
    resfinder_version: str = "4.7.2"
    resfinder_db_commit: str = "eecf0aa207594fe6d51badf808473de62b28cb06"
    resfinder_db_version: str = "2.6.0"
    pointfinder_db_commit: str = "44ce624a806c6d2b70f7e39841a5f9cb4d9010aa"
    pointfinder_db_version: str = "4.1.1"
    amrfinder_version: str = "4.2.7"
    amrfinder_db_version: str = "2026-05-15.1"
    amrfinder_image: str = "ncbi/amr:4.2.7-2026-05-15.1"
    result_schema_version: str = "2"
    pipeline_version: str = "multi-pathogen-ast-1"


TOOL_PINNING = ToolPinning()
