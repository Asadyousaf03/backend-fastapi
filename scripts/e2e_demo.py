#!/usr/bin/env python
"""Multi-pathogen end-to-end smoke test (fixture mode by default).

Runs E. coli and S. aureus analyses against the local FastAPI app using
committed golden ResFinder/AMRFinderPlus fixtures so Windows/CI can verify
without bioinformatics binaries.

Usage:
    .\\.venv\\Scripts\\python.exe scripts\\e2e_demo.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("TOOL_EXECUTION_MODE", "fixture")
os.environ.setdefault("ALLOW_FIXTURE_MODE", "true")
os.environ.setdefault("REQUIRE_REAL_TOOLS", "true")
os.environ.setdefault("ENABLE_DEMO_FALLBACK", "false")
os.environ.setdefault("COMPUTE_BACKEND", "local")
os.environ.setdefault("STORAGE_BACKEND", "local")
os.environ.setdefault("FIXTURE_DIR", str(ROOT / "tests" / "fixtures" / "tools"))

from config import get_settings

get_settings.cache_clear()

from fastapi.testclient import TestClient

from main import app


def _run_one(client: TestClient, *, organism: str, sample_name: str, fasta: Path) -> None:
    content = fasta.read_bytes()
    meta = {
        "sample_name": sample_name,
        "organism": organism,
        "read_type": "assembly",
        "file_format": "fasta",
        "notes": "fixture e2e",
    }
    upload = client.post(
        "/api/v2/uploads",
        json={
            "filename": fasta.name,
            "content_type": "application/octet-stream",
            "size_bytes": len(content),
            "metadata": meta,
        },
    )
    upload.raise_for_status()
    payload = upload.json()
    print("upload", organism, payload["upload_id"])

    put = client.put(
        f"/api/v2/uploads/{payload['upload_id']}/content",
        files={"file": (fasta.name, content, "application/octet-stream")},
    )
    assert put.status_code == 204, put.text

    created = client.post(
        "/api/v2/analyses",
        json={
            "upload_id": payload["upload_id"],
            "object_key": payload["object_key"],
            "metadata": meta,
        },
    )
    created.raise_for_status()
    analysis_id = created.json()["analysis_id"]
    print("analysis", organism, analysis_id)

    body = None
    for _ in range(80):
        status = client.get(f"/api/v2/analyses/{analysis_id}").json()
        print("status", status["status"], status.get("current_stage"), status["progress"])
        if status["status"] == "completed":
            body = client.get(f"/api/v2/analyses/{analysis_id}/result").json()
            break
        if status["status"] == "failed":
            raise RuntimeError(status.get("error") or "analysis failed")
        time.sleep(0.25)

    if body is None:
        raise RuntimeError(f"Timed out waiting for {organism}")

    resistant = [c["drug"] for c in body["antibiogram"] if c.get("label") == "R"]
    print(
        "result",
        organism,
        "schema",
        body["schema_version"],
        "R_drugs",
        resistant[:8],
        "evidence",
        len(body.get("evidence") or []),
        "tool_runs",
        [r["tool"] + ":" + r["status"] for r in body.get("tool_runs") or []],
    )


def main() -> None:
    ecoli = ROOT / "data" / "samples" / "demo_ecoli_cipro_r.fasta"
    saureus = ROOT / "data" / "samples" / "demo_saureus.fasta"
    if not saureus.exists():
        # Minimal assembly-length FASTA for fixture-mode S. aureus path.
        seq = ("ATGC" * 2500)
        saureus.write_text(f">demo_saureus\n{seq}\n", encoding="utf-8")

    with TestClient(app) as client:
        health = client.get("/health")
        health.raise_for_status()
        print("health", health.json())
        caps = client.get("/api/v2/capabilities")
        caps.raise_for_status()
        print("capabilities mode", caps.json().get("mode"), "species", len(caps.json()["species"]))
        ready = client.get("/ready")
        ready.raise_for_status()
        print("ready", ready.json().get("ready"))

        _run_one(client, organism="Escherichia coli", sample_name="demo-ecoli", fasta=ecoli)
        _run_one(
            client,
            organism="Staphylococcus aureus",
            sample_name="demo-saureus",
            fasta=saureus,
        )


if __name__ == "__main__":
    main()
