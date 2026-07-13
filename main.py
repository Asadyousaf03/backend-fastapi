import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.agent_logs import router as agent_logs_router
from schemas import AnalyzeRequest, AnalyzeResponse

app = FastAPI(title="Hack Nation AI API")
app.include_router(agent_logs_router)

default_origins = "http://localhost:3000,http://127.0.0.1:3000"
cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", default_origins).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=os.getenv("CORS_ORIGIN_REGEX", r"https://.*\.vercel\.app"),
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
