import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from schemas import AnalyzeRequest, AnalyzeResponse

app = FastAPI(title="AI Hackathon API")

cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    return AnalyzeResponse(
        status="success",
        summary=f"Analysis complete for: {request.query}",
        actions=[
            "Review patient intake notes",
            "Schedule follow-up within 48 hours",
            "Flag for clinical review",
        ],
        confidence_score=0.92,
    )
