# Live demo (presentation)

## What's live

- **API (MedIQ / Cloud Run):** https://genomic-ast-api-67343763423.us-central1.run.app  
- **Project:** `gen-lang-client-0182169919`  
- **Auth:** HospitALL org policy blocks public Cloud Run (`allUsers`). The Next.js `/api/backend` proxy uses a service-account ID token so the UI works without exposing the API.

## Demo mode

- Container includes **real ResFinder + AMRFinderPlus** (see `/ready`).
- Live service currently uses **fixture execution mode** so short demo FASTAs still return a rich multi-drug antibiogram (cipro/ampicillin/etc.).
- Real-tool execution was verified end-to-end on Cloud Run earlier (tools `success`); short demo assemblies produce sparse calls, so fixture mode is used for presentation impact.
- **Gemini** key is installed for clinical interpretation (falls back to deterministic text if the model call fails).

## Run frontend locally

```powershell
cd D:\Projects\frontend-nextjs
npm run dev
```

Open http://localhost:3000  
`.env.local` already points at the Cloud Run proxy.

## Vercel env vars (required)

```
NEXT_PUBLIC_API_URL=/api/backend
CLOUD_RUN_URL=https://genomic-ast-api-67343763423.us-central1.run.app
GCP_SA_JSON=<base64 of .secrets/genomic-ast-invoker.json>
```

## 60-second script

1. Open the app → pick **Escherichia coli** → upload `backend-fastapi/data/samples/demo_ecoli_cipro_r.fasta`
2. Watch stages: QC → species → tools → reconcile → interpretation
3. Show antibiogram: ciprofloxacin / ampicillin resistance signals + evidence
4. Repeat with **Staphylococcus aureus** + `demo_saureus.fasta`
5. Optional: hit `/ready` (via proxy) to show pinned tool versions

## Switch back to real-tool inference

```powershell
gcloud run services update genomic-ast-api --project=gen-lang-client-0182169919 --region=us-central1 --update-env-vars "TOOL_EXECUTION_MODE=real,ALLOW_FIXTURE_MODE=false,REQUIRE_REAL_TOOLS=true"
```

Use longer real assemblies for meaningful calls.
