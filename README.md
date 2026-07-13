# AI Hackathon — Backend

FastAPI service deployed as a separate Vercel project. No credit card required on the Hobby plan.

## Prerequisites

- Python 3.12+
- Node.js 18+ (for `vercel dev` optional)
- Git

## Local development

```bash
git clone https://github.com/Asadyousaf03/backend-fastapi.git
cd backend-fastapi
python -m venv .venv
```

**Windows (PowerShell)**

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**macOS / Linux**

```bash
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

API: [http://localhost:8000](http://localhost:8000)  
Docs: [http://localhost:8000/docs](http://localhost:8000/docs)

## Deploy to Vercel (recommended)

Deploy this repo as its own Vercel project — separate from the frontend.

1. Go to [vercel.com/new](https://vercel.com/new) and import `Asadyousaf03/backend-fastapi`.
2. Vercel auto-detects FastAPI from `main.py`. No build settings needed.
3. Add an environment variable (update after frontend is deployed):

```
CORS_ORIGINS=http://localhost:3000,https://your-frontend.vercel.app
```

4. Deploy. Copy your backend URL, e.g. `https://backend-fastapi.vercel.app`.
5. Set that URL as `NEXT_PUBLIC_API_URL` in the frontend Vercel project.

Test: `GET https://your-backend.vercel.app/health` → `{"status":"ok"}`

## API

### `POST /api/analyze`

**Request**

```json
{ "query": "Patient presents with elevated blood pressure" }
```

**Response**

```json
{
  "status": "success",
  "summary": "Analysis complete for: Patient presents with elevated blood pressure",
  "actions": [
    "Review patient intake notes",
    "Schedule follow-up within 48 hours",
    "Flag for clinical review"
  ],
  "confidence_score": 0.92
}
```

## Project structure

```
backend-fastapi/
├── main.py           # FastAPI app (Vercel entrypoint)
├── schemas.py        # Pydantic models
├── requirements.txt
├── vercel.json       # Vercel function config
└── .venv/            # Local only (not committed)
```

## Alternative hosts

`render.yaml` is included if you later use Render with a paid or verified account. For hackathon demos, Vercel is the simplest no-card option for both repos.
