# Hack Nation AI — Multi-Pathogen Genomic AST Backend

FastAPI service that runs **ResFinder 4.7.2** (primary genotype→phenotype inference) and **AMRFinderPlus 4.2.7** (independent genotypic corroboration) to produce multi-drug antibiograms for supported bacterial panels.

**Research use only. Not a clinical diagnostic.**  
AMRFinderPlus corroborates genotype evidence; it does **not** validate phenotype. True accuracy requires genome + phenotypic AST/MIC datasets.

Pairs with: [frontend-nextjs](https://github.com/Asadyousaf03/frontend-nextjs).

## Architecture

```text
Upload FASTA → API job → Storage/DB → Worker (local Docker or Modal)
  → QC → selected species panel
  → ResFinder (primary) + AMRFinderPlus (corroboration)
  → per-drug reconciliation → versioned antibiogram + SSE
```

| Endpoint | Role |
|---|---|
| `GET /health` | Liveness |
| `GET /ready` | Tool/database readiness |
| `GET /api/v2/capabilities` | Species panels, pins, tool readiness |
| `POST /api/v2/uploads` | Create upload slot |
| `PUT /api/v2/uploads/{id}/content` | Upload assembled FASTA |
| `POST /api/v2/analyses` | Enqueue job (`202`) |
| `GET /api/v2/analyses/{id}` | Status |
| `GET /api/v2/analyses/{id}/events` | SSE progress |
| `GET /api/v2/analyses/{id}/result` | `AnalysisResultV2` antibiogram |

`/api/v1/*` remains for compatibility. This release accepts **assembled FASTA only**.

### Pipeline stages (SSE)

`queued` → `qc` → `species` → `resfinder` → `amrfinderplus` → `reconcile` → `interpretation` → `completed` / `failed`

## Supported species panels

Escherichia coli, Salmonella, Campylobacter jejuni/coli, Enterococcus faecium/faecalis, Staphylococcus aureus, Mycobacterium tuberculosis.

Organism must be **user-selected** (no taxonomic auto-detection in this release).

## Pinned scientific runtime

| Component | Pin |
|---|---|
| ResFinder | `4.7.2` |
| ResFinder DB | commit `eecf0aa…` (`2.6.0`) |
| PointFinder DB | commit `44ce624…` (`4.1.1`) |
| AMRFinderPlus | `4.2.7` / DB `2026-05-15.1` |

Never update databases during a user job.

## Local setup (API only, fixture mode)

Useful on Windows without bioinformatics binaries:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# In .env:
# TOOL_EXECUTION_MODE=fixture
# ALLOW_FIXTURE_MODE=true
# REQUIRE_REAL_TOOLS=true
uvicorn main:app --reload --port 8001
```

Fixture mode loads golden ResFinder/AMRFinder outputs from `tests/fixtures/tools/` and is for CI/demo only—not production inference.

```powershell
pytest -q
python scripts\e2e_demo.py
```

## Local setup (real tools via Docker)

```powershell
docker compose up --build
```

This builds `Dockerfile.tools` (ResFinder + AMRFinderPlus + pinned DBs) and exposes the API on port **8001**. Health: `GET /ready`.

## Production compute (Modal)

1. Create Modal secrets `genomic-ast-db` (`DATABASE_URL`) and `genomic-ast-storage` (`STORAGE_BACKEND`, `S3_*`).
2. Set API `COMPUTE_BACKEND=modal`, Postgres `DATABASE_URL`, and S3 storage.
3. Deploy: `modal deploy modal_app/app.py`
4. Modal dispatch **fails closed**—no silent local fallback.

## Environment

See `.env.example`. Important variables:

| Variable | Purpose |
|---|---|
| `REQUIRE_REAL_TOOLS` | Fail closed when tools unavailable (`true` in production) |
| `TOOL_EXECUTION_MODE` | `real` or `fixture` |
| `RESFINDER_DB` / `POINTFINDER_DB` / `AMRFINDER_DB` | Pinned DB paths |
| `COMPUTE_BACKEND` | `local` or `modal` |
| `STORAGE_BACKEND` | `local` or `s3` |
| `DATABASE_URL` | SQLite (dev) or Postgres (prod) |

Schema evolution: lightweight `db/migrate.py` on startup + Alembic under `alembic/` (`alembic upgrade head`).

## Demo samples

- `data/samples/demo_ecoli_cipro_r.fasta`
- `data/samples/demo_saureus.fasta` (created by e2e if missing)

## Layout

```
main.py                 App, /health, /ready, capabilities
config.py               Env settings
routes/                 Upload + analysis APIs (v1/v2)
services/pipeline.py    Fail-closed orchestration
services/tools/         ResFinder + AMRFinderPlus adapters
services/species.py     Supported panels
services/reconciliation.py
modal_app/              Modal worker image + spawn
Dockerfile.tools        Pinned scientific runtime
docker-compose.yml      Local real-tool stack
alembic/                Migrations
tests/                  Fixture/unit/e2e tests
PROJECT_HANDOFF.md      Contributor roadmap
```

## Safety rules

- Failed/unavailable tools never become “susceptible” or “no resistance.”
- Empty determinant lists yield `unknown` / explicit no-call states unless ResFinder issues a phenotype call.
- Every result includes tool/database versions and research-use disclaimer.
