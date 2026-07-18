from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from db.models import AnalysisEventRecord
from db.session import SessionLocal
from main import app


def main() -> None:
    fasta = Path("data/samples/demo_ecoli_cipro_r.fasta").read_bytes()
    with TestClient(app) as client:
        up = client.post(
            "/api/v1/uploads",
            json={
                "filename": "demo_r.fasta",
                "content_type": "application/octet-stream",
                "size_bytes": len(fasta),
                "metadata": {
                    "sample_name": "demo-r",
                    "organism": "Escherichia coli",
                    "read_type": "assembly",
                    "file_format": "fasta",
                },
            },
        ).json()
        client.put(
            f"/api/v1/uploads/{up['upload_id']}/content",
            files={"file": ("demo_r.fasta", fasta, "application/octet-stream")},
        )
        created = client.post(
            "/api/v1/analyses",
            json={
                "upload_id": up["upload_id"],
                "object_key": up["object_key"],
                "metadata": {
                    "sample_name": "demo-r",
                    "organism": "Escherichia coli",
                    "read_type": "assembly",
                    "file_format": "fasta",
                },
            },
        ).json()
        aid = created["analysis_id"]
        for _ in range(40):
            st = client.get(f"/api/v1/analyses/{aid}").json()
            print("status", st)
            if st["status"] in {"completed", "failed"}:
                break
            time.sleep(0.4)

    db = SessionLocal()
    rows = db.scalars(
        select(AnalysisEventRecord)
        .where(AnalysisEventRecord.analysis_id == aid)
        .order_by(AnalysisEventRecord.sequence)
    ).all()
    for row in rows:
        print(row.sequence, row.stage, row.level, row.message)


if __name__ == "__main__":
    main()
