# Live demo (presentation-ready)

## Live URLs

| Piece | URL |
|---|---|
| **Frontend** | https://frontend-nextjs-wheat.vercel.app |
| **API** | https://genomic-ast-api-n5yblk32pa-uc.a.run.app |
| Health | https://genomic-ast-api-n5yblk32pa-uc.a.run.app/health |
| Ready | https://genomic-ast-api-n5yblk32pa-uc.a.run.app/ready |

**GCP:** `gen-lang-client-0182169919` · **service:** `genomic-ast-api` · **region:** `us-central1`

## Status (one sentence)

Live demo runs **real ResFinder + AMRFinderPlus** on Cloud Run (public via `--no-invoker-iam-check`); fixture mode remains available in code for local/CI only.

## 60-second demo script

1. Open https://frontend-nextjs-wheat.vercel.app  
2. Select **Escherichia coli**  
3. Upload `data/samples/demo_ecoli_cipro_r.fasta`  
4. Run → watch QC → ResFinder → AMRFinderPlus → antibiogram report  
5. Optional: **S. aureus** + `demo_saureus.fasta`  

Cold start tip: first hit after idle can take ~20–40s.

Verified live: E. coli FASTA completed with **schema v2** and a multi-drug antibiogram (~96 calls).
