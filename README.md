# Hack Nation AI — Genomic AST Backend

FastAPI service for **E. coli ciprofloxacin** genomic antimicrobial susceptibility prediction.

**Research use only. Not a clinical diagnostic.**

## Architecture

- `POST /api/v1/uploads` — create upload slot (local PUT or S3 presign)
- `PUT /api/v1/uploads/{id}/content` — upload FASTA/FASTQ
- `POST /api/v1/analyses` — enqueue async analysis (`202` + `analysis_id`)
- `GET /api/v1/analyses/{id}` — status
- `GET /api/v1/analyses/{id}/events` — SSE progress (`Last-Event-ID` supported)
- `GET /api/v1/analyses/{id}/result` — final report (QC, R/S, variants, SHAP, interpretation)

Heavy compute runs locally (threaded) or on **Modal** when `COMPUTE_BACKEND=modal`.

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

## Environment

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLite (default) or Postgres |
| `STORAGE_BACKEND` | `local` or `s3` |
| `COMPUTE_BACKEND` | `local` or `modal` |
| `GEMINI_API_KEY` | Optional clinical interpretation |
| `AMRPREDICTOR_MODEL_DIR` | Path to AMRpredictor weights |
| `CORS_ORIGINS` | Comma-separated frontend origins |

## ML core

1. Download AMRpredictor models from [Zenodo 16213507](https://zenodo.org/records/16213507)
2. Place E. coli ciprofloxacin XGBoost weights under `data/models/amrpredictor/`
3. Optional: install `amrfinder` for mechanistic corroboration

Without weights, the pipeline uses a transparent heuristic + marker scan (demo fallback) and still returns the full report schema.

## Validation

```powershell
python -m validation.run_validation
```

Produces lineage-aware metrics with EUCAST ATU (MIC 0.5) handling.

## Modal deploy

```powershell
modal deploy modal_app/app.py
```

Set `COMPUTE_BACKEND=modal` and provide `DATABASE_URL` accessible from Modal.
