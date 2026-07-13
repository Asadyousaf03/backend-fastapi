# AI Hackathon — Backend

FastAPI service deployed on Render. Pairs with the Next.js frontend on Vercel.

## Prerequisites

- Python 3.12+
- Git
- [Render](https://render.com) account (Hobby workspace)

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

## Deploy to Render

### Option A — Blueprint (uses `render.yaml`)

1. Go to [dashboard.render.com](https://dashboard.render.com).
2. Click **New +** → **Blueprint**.
3. Connect GitHub and select `Asadyousaf03/backend-fastapi`.
4. Review the service config (plan: **Free**) and click **Apply**.

### Option B — Manual Web Service (recommended if Blueprint asks for payment)

1. **New +** → **Web Service** (not Blueprint).
2. Connect `Asadyousaf03/backend-fastapi`, branch `main`.
3. Use these settings:

| Setting | Value |
|---|---|
| Name | `backend-fastapi` |
| Region | closest to you |
| Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Instance Type | **Free** |

4. Add environment variable (update after frontend deploy):

```
CORS_ORIGINS=http://localhost:3000,https://your-frontend.vercel.app
```

5. Click **Create Web Service**.

### After deploy

Copy your Render URL, e.g. `https://backend-fastapi.onrender.com`.

Test:

```
GET https://backend-fastapi.onrender.com/health
```

Expected: `{"status":"ok"}`

Set this URL as `NEXT_PUBLIC_API_URL` in your Vercel frontend project.

### Free tier notes

- Service spins down after ~15 minutes of inactivity.
- First request after idle may take 30–60 seconds (cold start).
- If Render asks for a card, it is usually optional verification on the Hobby plan — select **Free** instance type and skip payment if possible. A $1 hold may appear and is refunded.

### `GET /api/agent-logs`

Server-Sent Events stream of simulated agent execution steps. Used by the frontend live console during analysis.

```
data: ⚡ Initializing Multi-Agent Orchestrator...

data: 🔍 Inspecting database via pgvector context...
```

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
├── main.py           # FastAPI app and routes
├── schemas.py        # Pydantic models
├── requirements.txt
├── render.yaml       # Render Blueprint config
├── runtime.txt       # Python version
└── .venv/            # Local only (not committed)
```
