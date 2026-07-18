#!/usr/bin/env python
"""End-to-end smoke test against the local FastAPI app."""

from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from main import app


def main() -> None:
    fasta = Path("data/samples/demo_ecoli_cipro_r.fasta").read_bytes()
    with TestClient(app) as client:
        health = client.get("/health")
        health.raise_for_status()
        print("health", health.json())

        upload = client.post(
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
        )
        upload.raise_for_status()
        payload = upload.json()
        print("upload", payload["upload_id"])

        put = client.put(
            f"/api/v1/uploads/{payload['upload_id']}/content",
            files={"file": ("demo_r.fasta", fasta, "application/octet-stream")},
        )
        assert put.status_code == 204, put.text

        created = client.post(
            "/api/v1/analyses",
            json={
                "upload_id": payload["upload_id"],
                "object_key": payload["object_key"],
                "metadata": {
                    "sample_name": "demo-r",
                    "organism": "Escherichia coli",
                    "read_type": "assembly",
                    "file_format": "fasta",
                },
            },
        )
        created.raise_for_status()
        analysis_id = created.json()["analysis_id"]
        print("analysis", analysis_id)

        for _ in range(60):
            status = client.get(f"/api/v1/analyses/{analysis_id}").json()
            print(
                "status",
                status["status"],
                status.get("current_stage"),
                status["progress"],
            )
            if status["status"] in {"completed", "failed"}:
                break
            time.sleep(0.5)

        result = client.get(f"/api/v1/analyses/{analysis_id}/result")
        result.raise_for_status()
        body = result.json()
        print(
            "result",
            body["susceptibility"]["label"],
            body["susceptibility"]["probability_resistant"],
            len(body["variants"]),
            len(body["shap_features"]),
        )


if __name__ == "__main__":
    main()
