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

CORS is enabled for `http://localhost:3000` so the Next.js frontend can call this API during local development.

## Project structure

```
backend-fastapi/
├── main.py           # FastAPI app and routes
├── schemas.py        # Pydantic request/response models
├── requirements.txt  # Python dependencies
└── .venv/            # Local virtual environment (not committed)
```
