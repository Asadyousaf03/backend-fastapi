# AI Hackathon — Backend

FastAPI service that exposes a mock AI agent analysis endpoint for local development.

## Prerequisites

- Python 3.11 or newer
- Git

## Clone and setup

```bash
git clone <repository-url>
cd backend-fastapi
```

Create and activate a virtual environment:

**Windows (PowerShell)**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run the server

With the virtual environment activated:

```bash
uvicorn main:app --reload --port 8000
```

The API will be available at [http://localhost:8000](http://localhost:8000).

Interactive docs: [http://localhost:8000/docs](http://localhost:8000/docs)

## API

### `POST /api/analyze`

Accepts a JSON body with a `query` string and returns a mock agent response.

**Request**

```json
{
  "query": "Patient presents with elevated blood pressure"
}
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

CORS is enabled for `http://localhost:3000` by default. Set the `CORS_ORIGINS` environment variable to allow additional frontend URLs (comma-separated).

## Deploy to Render

1. Go to [render.com](https://render.com) and sign in with GitHub.
2. Click **New +** → **Blueprint** (uses `render.yaml`) **or** **Web Service** (manual setup below).
3. Connect the `Asadyousaf03/backend-fastapi` repository.
4. Use these settings for a manual Web Service:

| Setting        | Value                                              |
| -------------- | -------------------------------------------------- |
| Name           | `backend-fastapi`                                  |
| Region         | closest to you                                     |
| Branch         | `main`                                             |
| Runtime        | Python 3                                           |
| Build Command  | `pip install -r requirements.txt`                  |
| Start Command  | `uvicorn main:app --host 0.0.0.0 --port $PORT`     |
| Plan           | Free                                               |

5. Add an environment variable once your frontend is deployed:

```
CORS_ORIGINS=http://localhost:3000,https://your-app.vercel.app
```

6. Click **Create Web Service**. Render will build and deploy automatically.
7. Copy your live API URL (e.g. `https://backend-fastapi.onrender.com`) and set it in Vercel as `NEXT_PUBLIC_API_URL`.

Health check: `GET /health` returns `{"status":"ok"}`.

**Note:** The free tier spins down after inactivity. The first request after idle may take 30–60 seconds.

## Project structure

```
backend-fastapi/
├── main.py           # FastAPI app and routes
├── schemas.py        # Pydantic request/response models
├── requirements.txt  # Python dependencies
├── render.yaml       # Render Blueprint config
├── runtime.txt       # Python version for Render
└── .venv/            # Local virtual environment (not committed)
```
