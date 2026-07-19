from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Fixture mode for CI without bioinformatics binaries.
import os

os.environ["TOOL_EXECUTION_MODE"] = "fixture"
os.environ["ALLOW_FIXTURE_MODE"] = "true"
os.environ["REQUIRE_REAL_TOOLS"] = "true"
os.environ["ENABLE_DEMO_FALLBACK"] = "false"
os.environ["COMPUTE_BACKEND"] = "local"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["DATABASE_URL"] = "sqlite:///./data/test_genomic_ast.db"
os.environ["FIXTURE_DIR"] = str(Path(__file__).parent / "fixtures" / "tools")

from config import get_settings

get_settings.cache_clear()

from main import app
from services.species import get_species, require_species
from services.tools.amrfinderplus import parse_amrfinder_tsv_file
from services.tools.resfinder import parse_resfinder_json_file
from services.reconciliation import reconcile
from services.tools.resfinder import load_fixture as load_rf
from services.tools.amrfinderplus import load_fixture as load_af


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    from db.session import init_db

    init_db()
    with TestClient(app) as test_client:
        yield test_client


def _long_fasta(path: Path, bases: int = 5000) -> None:
    seq = ("ATGC" * (bases // 4 + 1))[:bases]
    path.write_text(f">demo\n{seq}\n", encoding="utf-8")


def test_species_registry():
    assert get_species("E. coli") is not None
    assert get_species("Staphylococcus aureus").organism_id == "staphylococcus_aureus"
    with pytest.raises(ValueError):
        require_species("Unknownium inventus")


def test_parse_resfinder_and_amrfinder_fixtures():
    rf_path = Path("tests/fixtures/tools/escherichia_coli/resfinder.json")
    af_path = Path("tests/fixtures/tools/escherichia_coli/amrfinder.tsv")
    phenotypes, hits = parse_resfinder_json_file(rf_path)
    assert any(p.drug.lower() == "ciprofloxacin" and p.label == "R" for p in phenotypes)
    assert any(h.gene == "gyrA" for h in hits)
    af_hits = parse_amrfinder_tsv_file(af_path)
    assert any(h.gene.startswith("gyrA") or "gyrA" in h.gene for h in af_hits)


def test_reconciliation_concordant_and_unknown():
    panel = require_species("Escherichia coli")
    rf = load_rf(Path("tests/fixtures/tools/escherichia_coli/resfinder.json"))
    af = load_af(Path("tests/fixtures/tools/escherichia_coli/amrfinder.tsv"))
    calls, evidence, tool_runs = reconcile(panel, rf, af)
    assert tool_runs[0].tool == "resfinder"
    assert tool_runs[1].tool == "amrfinderplus"
    cipro = next(c for c in calls if c.drug.lower() == "ciprofloxacin")
    assert cipro.label == "R"
    assert cipro.agreement in {"concordant", "single_source", "complementary"}
    assert evidence


def test_capabilities_v2(client):
    response = client.get("/api/v2/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == "2"
    assert data["supported_file_formats"] == ["fasta"]
    assert len(data["species"]) >= 5
    assert data["pinned"]["resfinder"] == "4.7.2"


def test_ready_endpoint(client):
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["ready"] is True


def test_e2e_ecoli_fixture_antibiogram(client, tmp_path):
    fasta = tmp_path / "ecoli.fasta"
    _long_fasta(fasta, 8000)
    content = fasta.read_bytes()
    meta = {
        "sample_name": "demo-ecoli",
        "organism": "Escherichia coli",
        "platform": None,
        "read_type": "assembly",
        "file_format": "fasta",
        "notes": None,
    }
    upload = client.post(
        "/api/v2/uploads",
        json={
            "filename": "ecoli.fasta",
            "content_type": "application/octet-stream",
            "size_bytes": len(content),
            "metadata": meta,
        },
    )
    assert upload.status_code == 200, upload.text
    upload_body = upload.json()
    put = client.put(
        f"/api/v2/uploads/{upload_body['upload_id']}/content",
        files={"file": ("ecoli.fasta", content, "application/octet-stream")},
    )
    assert put.status_code == 204

    created = client.post(
        "/api/v2/analyses",
        json={
            "upload_id": upload_body["upload_id"],
            "object_key": upload_body["object_key"],
            "metadata": meta,
        },
    )
    assert created.status_code == 202, created.text
    analysis_id = created.json()["analysis_id"]

    # Local compute runs in a daemon thread; poll for completion.
    import time

    result = None
    for _ in range(40):
        status = client.get(f"/api/v2/analyses/{analysis_id}")
        assert status.status_code == 200
        body = status.json()
        if body["status"] == "completed":
            result = client.get(f"/api/v2/analyses/{analysis_id}/result")
            break
        if body["status"] == "failed":
            pytest.fail(body.get("error") or "analysis failed")
        time.sleep(0.25)
    assert result is not None and result.status_code == 200
    payload = result.json()
    assert payload["schema_version"] == "2"
    assert payload["organism"]["organism_id"] == "escherichia_coli"
    assert payload["antibiogram"]
    assert any(c["drug"].lower() == "ciprofloxacin" and c["label"] == "R" for c in payload["antibiogram"])
    assert payload["tool_runs"]
    assert all(run["status"] == "success" for run in payload["tool_runs"])


def test_reject_unsupported_organism(client, tmp_path):
    fasta = tmp_path / "x.fasta"
    _long_fasta(fasta)
    content = fasta.read_bytes()
    response = client.post(
        "/api/v2/uploads",
        json={
            "filename": "x.fasta",
            "content_type": "application/octet-stream",
            "size_bytes": len(content),
            "metadata": {
                "sample_name": "bad",
                "organism": "Unknownium inventus",
                "read_type": "assembly",
                "file_format": "fasta",
            },
        },
    )
    assert response.status_code == 400


def test_reject_fastq(client):
    response = client.post(
        "/api/v2/uploads",
        json={
            "filename": "reads.fastq",
            "content_type": "application/octet-stream",
            "size_bytes": 100,
            "metadata": {
                "sample_name": "reads",
                "organism": "Escherichia coli",
                "read_type": "short",
                "file_format": "fastq",
            },
        },
    )
    assert response.status_code == 400


def test_reconciliation_discordant_and_tool_failed():
    from services.tools.amrfinderplus import AmrfinderHit, AmrfinderResult
    from services.tools.resfinder import ResFinderPhenotype, ResFinderResult

    panel = require_species("Escherichia coli")
    rf_ok = ResFinderResult(
        status="success",
        phenotypes=[
            ResFinderPhenotype(
                drug="ciprofloxacin",
                drug_class="fluoroquinolone",
                label="S",
                genes=[],
            )
        ],
        hits=[],
        tool_run={
            "tool": "resfinder",
            "status": "success",
            "role": "primary_inference",
            "version": "4.7.2",
        },
    )
    af_r = AmrfinderResult(
        status="success",
        hits=[
            AmrfinderHit(
                evidence_id="amrfinderplus:gyra",
                gene="gyrA_S83L",
                mutation="S83L",
                identity=0.99,
                coverage=1.0,
                drug_class="QUINOLONE",
                subclass="CIPROFLOXACIN",
                method="POINTX",
                contig="contig1",
                start=100,
                end=120,
                strand="+",
                accession="ref",
                scope="core",
                element_type="AMR",
            )
        ],
        tool_run={
            "tool": "amrfinderplus",
            "status": "success",
            "role": "corroboration",
            "version": "4.2.7",
            "disclaimer": "Genotypic corroboration only; not phenotypic validation.",
        },
    )
    calls, _, _ = reconcile(panel, rf_ok, af_r)
    cipro = next(c for c in calls if c.drug.lower() == "ciprofloxacin")
    assert cipro.call_status == "conflicting"
    assert cipro.agreement == "discordant"

    rf_fail = ResFinderResult(
        status="failed",
        phenotypes=[],
        hits=[],
        tool_run={
            "tool": "resfinder",
            "status": "failed",
            "role": "primary_inference",
            "error": "boom",
        },
        error="boom",
    )
    af_fail = AmrfinderResult(
        status="unavailable",
        hits=[],
        tool_run={
            "tool": "amrfinderplus",
            "status": "unavailable",
            "role": "corroboration",
            "error": "missing",
        },
        error="missing",
    )
    failed_calls, _, tool_runs = reconcile(panel, rf_fail, af_fail)
    assert any(c.call_status == "tool_failed" for c in failed_calls)
    assert {r.status for r in tool_runs} == {"failed", "unavailable"}


def test_e2e_saureus_fixture_antibiogram(client, tmp_path):
    fasta = tmp_path / "saureus.fasta"
    _long_fasta(fasta, 8000)
    content = fasta.read_bytes()
    meta = {
        "sample_name": "demo-saureus",
        "organism": "Staphylococcus aureus",
        "platform": None,
        "read_type": "assembly",
        "file_format": "fasta",
        "notes": None,
    }
    upload = client.post(
        "/api/v2/uploads",
        json={
            "filename": "saureus.fasta",
            "content_type": "application/octet-stream",
            "size_bytes": len(content),
            "metadata": meta,
        },
    )
    assert upload.status_code == 200, upload.text
    upload_body = upload.json()
    put = client.put(
        f"/api/v2/uploads/{upload_body['upload_id']}/content",
        files={"file": ("saureus.fasta", content, "application/octet-stream")},
    )
    assert put.status_code == 204

    created = client.post(
        "/api/v2/analyses",
        json={
            "upload_id": upload_body["upload_id"],
            "object_key": upload_body["object_key"],
            "metadata": meta,
        },
    )
    assert created.status_code == 202, created.text
    analysis_id = created.json()["analysis_id"]

    import time

    result = None
    for _ in range(40):
        status = client.get(f"/api/v2/analyses/{analysis_id}")
        body = status.json()
        if body["status"] == "completed":
            result = client.get(f"/api/v2/analyses/{analysis_id}/result")
            break
        if body["status"] == "failed":
            pytest.fail(body.get("error") or "analysis failed")
        time.sleep(0.25)
    assert result is not None and result.status_code == 200
    payload = result.json()
    assert payload["schema_version"] == "2"
    assert payload["organism"]["organism_id"] == "staphylococcus_aureus"
    assert payload["antibiogram"]
    assert payload["tool_runs"]
