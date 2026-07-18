import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from db.session import init_db
from routes.analyses import router as analyses_router
from routes.uploads import router as uploads_router
from schemas import AnalyzeRequest, AnalyzeResponse


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


settings = get_settings()
# Ensure tables exist even when lifespan is not entered (e.g. some test clients).
init_db()
app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
app.include_router(uploads_router)
app.include_router(analyses_router)

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
    return {
        "status": "ok",
        "service": "genomic-ast",
        "compute_backend": settings.compute_backend,
        "storage_backend": settings.storage_backend,
    }


@app.post("/api/analyze", response_model=AnalyzeResponse, deprecated=True)
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    return AnalyzeResponse(
        status="deprecated",
        summary=(
            "Legacy endpoint retained for compatibility. "
            f"Use POST /api/v1/analyses for genomic AST. Query echoed: {request.query}"
        ),
        actions=[
            "POST /api/v1/uploads",
            "PUT upload content",
            "POST /api/v1/analyses",
        ],
        confidence_score=0.0,
    )
