# Hack Nation AI — Genomic AST Backend

FastAPI service for **E. coli ciprofloxacin** genomic antimicrobial susceptibility prediction.

**Research use only. Not a clinical diagnostic.**

Pairs with the Next.js frontend: [frontend-nextjs](https://github.com/Asadyousaf03/frontend-nextjs).

## Architecture

| Endpoint | Role |
|---|---|
| `GET /health` | Liveness + compute/storage backend |
| `POST /api/v1/uploads` | Create upload slot (local PUT or S3 presign) |
| `PUT /api/v1/uploads/{id}/content` | Upload FASTA/FASTQ bytes |
| `POST /api/v1/analyses` | Enqueue async job (`202` + `analysis_id`) |
| `GET /api/v1/analyses/{id}` | Status / stage / progress |
| `GET /api/v1/analyses/{id}/events` | SSE progress (`Last-Event-ID` supported) |
| `GET /api/v1/analyses/{id}/result` | Final report (QC, R/S, variants, SHAP, interpretation) |

Legacy `POST /api/analyze` remains deprecated for compatibility.

Heavy compute runs in a **local thread** or on **Modal** when `COMPUTE_BACKEND=modal` (`services/compute.py` → `services/pipeline.py`).

### Pipeline stages (SSE)

`queued` → `qc` → `assembly` → `species` → `features` → `ml` → `rules` → `interpretation` → `completed` (or `failed`).

Layout:

```
main.py                 App, CORS, health
config.py               Env-backed settings
routes/uploads.py       Upload API
routes/analyses.py      Analyses + SSE
services/pipeline.py    Job orchestration
services/ml_core.py     AMRpredictor / heuristic fallback
services/events.py      Progress event store
modal_app/              Modal deploy entrypoints
db/                     SQLAlchemy models + session
validation/             Lineage-aware metrics
data/samples/           Demo FASTA
```

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn main:app --reload --port 8001
```

Open docs at [http://localhost:8001/docs](http://localhost:8001/docs).

Use port **8001** so it matches the frontend README / `.env.example` (`PUBLIC_API_BASE`). Config still defaults `PUBLIC_API_BASE` to `8000` if unset — set it in `.env`.

## Environment

Copy `.env.example`. Important variables:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLite (default `sqlite:///./data/genomic_ast.db`) or Postgres |
| `STORAGE_BACKEND` | `local` or `s3` |
| `LOCAL_STORAGE_PATH` | Local upload root (default `./data/uploads`) |
| `PUBLIC_API_BASE` | Absolute base used in upload URLs (e.g. `http://localhost:8001`) |
| `COMPUTE_BACKEND` | `local` or `modal` |
| `ENABLE_DEMO_FALLBACK` | Heuristic path when model weights missing |
| `AMRPREDICTOR_MODEL_DIR` | Path to AMRpredictor weights |
| `CORS_ORIGINS` | Comma-separated frontend origins |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | Optional clinical interpretation text |
| `S3_*` | Required when `STORAGE_BACKEND=s3` |

Do not commit `.env`, `*.db`, `data/uploads/`, or model weight binaries.

## Demo FASTA

- `data/samples/demo_ecoli_cipro_r.fasta` — resistant-oriented demo
- `data/samples/demo_ecoli_cipro_s.fasta` — susceptible-oriented demo

Regenerate with `python scripts/make_demo_fasta.py` if needed.

## Scripts

```powershell
# Smoke test: upload → analyze → poll → print R/S (uses TestClient, no server required)
python scripts/e2e_demo.py

# Inspect a failed analysis record
python scripts/debug_failed.py

# Export OpenAPI snapshot
python scripts/export_openapi.py
```

## ML core

1. Download AMRpredictor models from [Zenodo 16213507](https://zenodo.org/records/16213507)
2. Place E. coli ciprofloxacin XGBoost weights under `data/models/amrpredictor/`
3. Optional: install `amrfinder` for mechanistic corroboration

Without weights, the pipeline uses a transparent heuristic + marker scan (demo fallback) and still returns the full report schema.

## Validation

```powershell
python -m validation.run_validation
```

Uses `data/validation/ecoli_cipro_ast.csv` and writes lineage-aware metrics (EUCAST ATU / MIC 0.5 handling) under `data/validation/`.

## Modal deploy

```powershell
modal deploy modal_app/app.py
```

Set `COMPUTE_BACKEND=modal` and provide a `DATABASE_URL` reachable from Modal.

## Render

See `render.yaml` for the hosted service blueprint. Point the frontend `NEXT_PUBLIC_API_URL` at the Render URL and allow the Vercel origin in CORS.
