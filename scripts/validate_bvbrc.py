"""Validate the live genomic-AST API against real BV-BRC genomes + lab phenotypes.

What it does
------------
1. Pulls a balanced batch of real bacterial genomes from BV-BRC that have
   laboratory antimicrobial susceptibility (AST) phenotypes.
2. Downloads each genome's contigs (FASTA) from the BV-BRC genome_sequence API.
3. Runs each genome through the deployed Cloud Run API (upload -> analyse).
4. Compares the API's predicted antibiogram (R/S) against the BV-BRC lab
   phenotype and prints an accuracy table, including the AST-standard
   categorical agreement / major error / very-major error metrics.

This is a concrete "validated against real data" result: every genome and
phenotype comes from a public, curated surveillance database (BV-BRC), and the
predictions come from the same live endpoint the demo uses.

Usage (from backend-fastapi with the venv active):
    python scripts/validate_bvbrc.py --genomes 8
    python scripts/validate_bvbrc.py --taxon 562 --organism "Escherichia coli" --genomes 10

Requires the invoker service-account key used by the live smoke test:
    D:\\Projects\\frontend-nextjs\\.secrets\\genomic-ast-invoker.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.parse
import urllib.request
import uuid
from collections import defaultdict

from google.auth.transport.requests import Request
from google.oauth2 import service_account

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
BASE = "https://genomic-ast-api-67343763423.us-central1.run.app"
SA_KEY = pathlib.Path(r"D:\Projects\frontend-nextjs\.secrets\genomic-ast-invoker.json")
BVBRC_API = "https://www.bv-brc.org/api"

# Map BV-BRC organism scientific name -> our API organism string.
ORGANISM_API_NAME = {
    "562": "Escherichia coli",
    "590": "Salmonella",
    "1280": "Staphylococcus aureus",
    "573": "Klebsiella pneumoniae",
}


# --------------------------------------------------------------------------
# Auth + HTTP helpers
# --------------------------------------------------------------------------
def _make_auth() -> dict[str, str]:
    creds = service_account.IDTokenCredentials.from_service_account_file(
        str(SA_KEY), target_audience=BASE
    )
    creds.refresh(Request())
    return {"Authorization": f"Bearer {creds.token}"}


def api_call(auth, method, path, data=None, headers=None, raw=False, timeout=300):
    h = dict(auth)
    if headers:
        h.update(headers)
    body = None
    if data is not None and not raw:
        body = json.dumps(data).encode()
        h["Content-Type"] = "application/json"
    elif raw:
        body = data
    req = urllib.request.Request(BASE + path, data=body, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = resp.read()
        if resp.status == 204 or not payload:
            return None
        return json.loads(payload.decode())


def bvbrc_get(endpoint: str, rql: str, accept: str = "application/json", timeout=120):
    url = f"{BVBRC_API}/{endpoint}/?{rql}"
    req = urllib.request.Request(url, headers={"Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    if accept == "application/json":
        return json.loads(data.decode())
    return data


# --------------------------------------------------------------------------
# Drug-name normalisation (BV-BRC <-> our panel)
# --------------------------------------------------------------------------
def norm_drug(name: str) -> str:
    n = (name or "").strip().lower()
    n = n.replace("/", "-").replace(" ", "-")
    aliases = {
        "trimethoprim-sulphamethoxazole": "trimethoprim-sulfamethoxazole",
        "co-trimoxazole": "trimethoprim-sulfamethoxazole",
        "sulphamethoxazole": "sulfamethoxazole",
        "sulfamethoxazole-trimethoprim": "trimethoprim-sulfamethoxazole",
    }
    return aliases.get(n, n)


def norm_pheno(value: str) -> str | None:
    v = (value or "").strip().lower()
    if v in {"resistant", "r", "non-susceptible", "nonsusceptible"}:
        return "R"
    if v in {"susceptible", "s", "sensitive", "susceptible-dose dependent"}:
        return "S"
    return None  # Intermediate / unknown -> skip


# --------------------------------------------------------------------------
# BV-BRC selection
# --------------------------------------------------------------------------
def pick_genomes(taxon: str, seed_antibiotic: str, n: int) -> list[dict]:
    """Return up to n genome dicts balanced across R/S for the seed antibiotic."""
    # Odd n: give the extra seat to Resistant so we still hit both classes.
    targets = {"Resistant": (n + 1) // 2, "Susceptible": n // 2}
    selected: dict[str, dict] = {}
    for phenotype in ("Resistant", "Susceptible"):
        need = max(1, targets[phenotype]) if n >= 1 else 0
        rql = (
            f"and(eq(taxon_id,{taxon}),eq(antibiotic,{seed_antibiotic}),"
            f"eq(resistant_phenotype,{phenotype}))"
            "&select(genome_id,genome_name,antibiotic,resistant_phenotype)"
            f"&limit({need * 4})"
        )
        rows = bvbrc_get("genome_amr", rql)
        added = 0
        for row in rows:
            gid = row["genome_id"]
            if gid in selected:
                continue
            selected[gid] = {
                "genome_id": gid,
                "genome_name": row.get("genome_name", gid),
                "seed_phenotype": phenotype,
            }
            added += 1
            if added >= need:
                break
    return list(selected.values())[:n]


def fetch_phenotypes(taxon: str, genome_id: str) -> dict[str, str]:
    """Return {normalised_drug: R/S} lab phenotypes for one genome."""
    rql = (
        f"and(eq(taxon_id,{taxon}),eq(genome_id,{genome_id}))"
        "&select(antibiotic,resistant_phenotype)"
        "&limit(200)"
    )
    rows = bvbrc_get("genome_amr", rql)
    out: dict[str, str] = {}
    for row in rows:
        drug = norm_drug(row.get("antibiotic", ""))
        label = norm_pheno(row.get("resistant_phenotype", ""))
        if drug and label:
            out[drug] = label  # last write wins; BV-BRC rarely conflicts per genome
    return out


def download_fasta(genome_id: str, timeout=300) -> bytes:
    rql = (
        f"eq(genome_id,{genome_id})"
        "&select(genome_id,accession,sequence)"
        "&limit(2000)"
    )
    return bvbrc_get(
        "genome_sequence", rql, accept="application/dna+fasta", timeout=timeout
    )


# --------------------------------------------------------------------------
# Run one genome through the live API
# --------------------------------------------------------------------------
def run_analysis(auth, organism: str, genome_id: str, fasta: bytes, poll=360) -> dict:
    auth = _make_auth()
    meta = {
        "sample_name": f"bvbrc_{genome_id}",
        "organism": organism,
        "platform": "illumina",
        "read_type": "assembly",
        "file_format": "fasta",
        "notes": f"BV-BRC validation {genome_id}",
    }
    filename = f"{genome_id}.fasta"
    up = api_call(
        auth,
        "POST",
        "/api/v2/uploads",
        {
            "filename": filename,
            "content_type": "application/octet-stream",
            "size_bytes": len(fasta),
            "metadata": meta,
        },
    )
    boundary = "----bound" + uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + fasta + f"\r\n--{boundary}--\r\n".encode()
    api_call(
        auth,
        "PUT",
        f"/api/v2/uploads/{up['upload_id']}/content",
        body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        raw=True,
        timeout=600,
    )
    analysis = api_call(
        auth,
        "POST",
        "/api/v2/analyses",
        {"upload_id": up["upload_id"], "object_key": up["object_key"], "metadata": meta},
    )
    aid = analysis["analysis_id"]
    status = None
    for i in range(poll):
        if i and i % 60 == 0:
            auth = _make_auth()
        status = api_call(auth, "GET", f"/api/v2/analyses/{aid}")
        if status["status"] in {"completed", "failed"}:
            break
        print(f"      ... status={status.get('status')} ({i+1}/{poll})", flush=True)
        time.sleep(5)
    if not status or status["status"] != "completed":
        raise RuntimeError(f"analysis {aid} did not complete: {(status or {}).get('error')}")
    return api_call(auth, "GET", f"/api/v2/analyses/{aid}/result")


def predictions_from_result(result: dict) -> dict[str, dict]:
    """Return {normalised_drug: {label, call_status}} from an API antibiogram."""
    out: dict[str, dict] = {}
    for call in result.get("antibiogram") or []:
        drug = norm_drug(call.get("drug", ""))
        if drug:
            out[drug] = {
                "label": call.get("label"),
                "call_status": call.get("call_status"),
            }
    return out


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Validate live AST API vs BV-BRC")
    ap.add_argument("--taxon", default="562", help="BV-BRC taxon_id (562 = E. coli)")
    ap.add_argument("--organism", default=None, help="Override API organism name")
    ap.add_argument("--seed-antibiotic", default="ciprofloxacin")
    ap.add_argument("--genomes", type=int, default=8, help="Number of genomes to test")
    ap.add_argument("--out", default="data/validation/bvbrc_live_results.json")
    args = ap.parse_args()

    organism = args.organism or ORGANISM_API_NAME.get(args.taxon, "Escherichia coli")
    print(f"== BV-BRC live validation ==")
    print(f"taxon={args.taxon} organism={organism!r} genomes={args.genomes}")
    print(f"endpoint={BASE}\n")

    auth = _make_auth()

    print("[1/3] Selecting genomes with lab AST phenotypes from BV-BRC...")
    genomes = pick_genomes(args.taxon, args.seed_antibiotic, args.genomes)
    print(f"      selected {len(genomes)} genomes\n")

    # comparison rows: (genome_id, drug, actual, predicted, call_status)
    rows: list[dict] = []
    genome_reports: list[dict] = []

    for i, g in enumerate(genomes, 1):
        gid = g["genome_id"]
        name = g["genome_name"]
        print(f"[2/3] ({i}/{len(genomes)}) {gid}  {name}")
        try:
            phenos = fetch_phenotypes(args.taxon, gid)
            if not phenos:
                print("      no usable phenotypes, skipping")
                continue
            print(f"      lab phenotypes: {len(phenos)} drugs; downloading FASTA...")
            fasta = download_fasta(gid)
            print(f"      FASTA {len(fasta)/1e6:.2f} MB; running analysis (real tools)...")
            result = run_analysis(auth, organism, gid, fasta)
            preds = predictions_from_result(result)
            matched = 0
            for drug, actual in phenos.items():
                pred = preds.get(drug)
                pred_label = pred["label"] if pred else None
                rows.append(
                    {
                        "genome_id": gid,
                        "drug": drug,
                        "actual": actual,
                        "predicted": pred_label,
                        "call_status": pred["call_status"] if pred else "not_in_panel",
                    }
                )
                if pred_label in {"R", "S"}:
                    matched += 1
            genome_reports.append(
                {"genome_id": gid, "genome_name": name, "lab_drugs": len(phenos), "predicted_calls": matched}
            )
            print(f"      compared {matched} drugs with an R/S prediction")
        except Exception as exc:  # noqa: BLE001 - keep the batch resilient
            print(f"      ERROR: {exc}")
        print()

    # ----------------------------------------------------------------------
    # Metrics
    # ----------------------------------------------------------------------
    comparable = [r for r in rows if r["predicted"] in {"R", "S"}]
    print("=" * 68)
    print("VALIDATION SUMMARY (predicted vs BV-BRC lab phenotype)")
    print("=" * 68)
    if not comparable:
        print("No comparable predictions were produced. Check tool mode / genomes.")
    else:
        correct = sum(1 for r in comparable if r["predicted"] == r["actual"])
        # AST-standard error rates
        vme = sum(1 for r in comparable if r["actual"] == "R" and r["predicted"] == "S")
        me = sum(1 for r in comparable if r["actual"] == "S" and r["predicted"] == "R")
        n_r = sum(1 for r in comparable if r["actual"] == "R")
        n_s = sum(1 for r in comparable if r["actual"] == "S")

        # per-drug breakdown
        by_drug: dict[str, list] = defaultdict(list)
        for r in comparable:
            by_drug[r["drug"]].append(r)
        print(f"\nPer-antibiotic accuracy:")
        print(f"  {'drug':<32}{'n':>4}{'correct':>9}{'acc':>7}")
        for drug in sorted(by_drug):
            items = by_drug[drug]
            c = sum(1 for r in items if r["predicted"] == r["actual"])
            print(f"  {drug:<32}{len(items):>4}{c:>9}{c/len(items):>7.0%}")

        print(f"\nOverall")
        print(f"  comparable calls        : {len(comparable)}")
        print(f"  categorical agreement   : {correct}/{len(comparable)} = {correct/len(comparable):.1%}")
        if n_r:
            print(f"  very major error (R->S) : {vme}/{n_r} = {vme/n_r:.1%}")
        if n_s:
            print(f"  major error (S->R)      : {me}/{n_s} = {me/n_s:.1%}")

    # coverage note
    not_called = [r for r in rows if r["predicted"] not in {"R", "S"}]
    print(f"\nCoverage")
    print(f"  genomes analysed        : {len(genome_reports)}")
    print(f"  lab phenotype rows      : {len(rows)}")
    print(f"  with R/S prediction     : {len(comparable)}")
    print(f"  no call / not in panel  : {len(not_called)}")

    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"genomes": genome_reports, "rows": rows}, indent=2), encoding="utf-8"
    )
    print(f"\nDetailed results written to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
