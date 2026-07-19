"""Scientific runtime readiness checks."""

from __future__ import annotations

from config import get_settings
from services.tools import amrfinderplus, resfinder
from services.tools.versions import TOOL_PINNING


def tool_readiness() -> dict[str, object]:
    settings = get_settings()
    rf = resfinder.check_availability(
        resfinder_db=settings.resfinder_db,
        pointfinder_db=settings.pointfinder_db,
    )
    af = amrfinderplus.check_availability(database=settings.amrfinder_db)
    fixture_mode = settings.tool_execution_mode == "fixture"
    ready = (rf.ready and af.ready) or (
        fixture_mode and settings.allow_fixture_mode
    )
    return {
        "ready": ready,
        "require_real_tools": settings.require_real_tools,
        "tool_execution_mode": settings.tool_execution_mode,
        "pinned": {
            "resfinder_version": TOOL_PINNING.resfinder_version,
            "resfinder_db_commit": TOOL_PINNING.resfinder_db_commit,
            "resfinder_db_version": TOOL_PINNING.resfinder_db_version,
            "pointfinder_db_commit": TOOL_PINNING.pointfinder_db_commit,
            "pointfinder_db_version": TOOL_PINNING.pointfinder_db_version,
            "amrfinder_version": TOOL_PINNING.amrfinder_version,
            "amrfinder_db_version": TOOL_PINNING.amrfinder_db_version,
            "result_schema_version": TOOL_PINNING.result_schema_version,
            "pipeline_version": TOOL_PINNING.pipeline_version,
        },
        "resfinder": {
            "ready": rf.ready,
            "executable": rf.executable,
            "version": rf.version,
            "database_path": rf.database_path,
            "database_version": rf.database_version,
            "errors": rf.errors,
        },
        "amrfinderplus": {
            "ready": af.ready,
            "executable": af.executable,
            "version": af.version,
            "database_path": af.database_path,
            "database_version": af.database_version,
            "errors": af.errors,
        },
        "input_formats": ["fasta"],
        "notes": [
            "ResFinder is the primary genotype-to-phenotype inference engine.",
            "AMRFinderPlus provides independent genotypic corroboration, not phenotypic validation.",
            "Assembled FASTA only in this release.",
        ],
    }
