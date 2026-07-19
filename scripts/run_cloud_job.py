from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.models import AnalysisRecord
from db.session import SessionLocal
from services.pipeline import run_analysis_job


def main() -> int:
    analysis_id = os.environ.get("ANALYSIS_ID")
    if not analysis_id:
        print("ANALYSIS_ID is required", file=sys.stderr)
        return 2

    run_analysis_job(analysis_id)

    with SessionLocal() as db:
        analysis = db.get(AnalysisRecord, analysis_id)
        if not analysis:
            print(f"Analysis {analysis_id} no longer exists", file=sys.stderr)
            return 3
        if analysis.status != "completed":
            print(
                f"Analysis {analysis_id} ended with status={analysis.status}: "
                f"{analysis.error or 'unknown pipeline error'}",
                file=sys.stderr,
            )
            return 1

    print(f"Analysis {analysis_id} completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
