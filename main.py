import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from db.session import init_db
from routes.analyses import router as analyses_router
from routes.analyses import router_v2 as analyses_router_v2
from routes.uploads import router as uploads_router
from routes.uploads import router_v2 as uploads_router_v2
from schemas import AnalyzeRequest, AnalyzeResponse, ApiCapabilitiesV2, SpeciesCapability
from services.species import capabilities_payload
from services.tools.readiness import tool_readiness
from services.tools.versions import TOOL_PINNING


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, version="2.0.0", lifespan=lifespan)
app.include_router(uploads_router)
app.include_router(uploads_router_v2)
app.include_router(analyses_router)
app.include_router(analyses_router_v2)

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
        "schema_version": TOOL_PINNING.result_schema_version,
    }


@app.get("/ready")
def ready() -> dict[str, object]:
    readiness = tool_readiness()
    status = "ready" if readiness["ready"] else "not_ready"
    return {"status": status, **readiness}


def _capabilities() -> ApiCapabilitiesV2:
    readiness = tool_readiness()
    mode = "fixture" if settings.tool_execution_mode == "fixture" else "tools-required"
    return ApiCapabilitiesV2(
        schema_version="2",
        mode=mode,  # type: ignore[arg-type]
        supported_file_formats=["fasta"],
        max_upload_bytes=settings.max_upload_bytes,
        compute_backend=settings.compute_backend,
        storage_backend=settings.storage_backend,
        require_real_tools=settings.require_real_tools,
        tools_ready=bool(readiness["ready"]),
        species=[SpeciesCapability.model_validate(item) for item in capabilities_payload()],
        pinned={
            "resfinder": TOOL_PINNING.resfinder_version,
            "resfinder_db": TOOL_PINNING.resfinder_db_version,
            "resfinder_db_commit": TOOL_PINNING.resfinder_db_commit,
            "pointfinder_db": TOOL_PINNING.pointfinder_db_version,
            "pointfinder_db_commit": TOOL_PINNING.pointfinder_db_commit,
            "amrfinderplus": TOOL_PINNING.amrfinder_version,
            "amrfinder_db": TOOL_PINNING.amrfinder_db_version,
            "pipeline": TOOL_PINNING.pipeline_version,
            "result_schema": TOOL_PINNING.result_schema_version,
        },
        notes=list(readiness.get("notes") or []),
        readiness=readiness,
    )


@app.get("/api/v1/capabilities")
@app.get("/api/v2/capabilities", response_model=ApiCapabilitiesV2)
def capabilities() -> ApiCapabilitiesV2:
    return _capabilities()


@app.post("/api/analyze", response_model=AnalyzeResponse, deprecated=True)
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    return AnalyzeResponse(
        status="deprecated",
        summary=(
            "Legacy endpoint retained for compatibility. "
            f"Use POST /api/v2/analyses for multi-pathogen genomic AST. Query echoed: {request.query}"
        ),
        actions=[
            "GET /api/v2/capabilities",
            "POST /api/v2/uploads",
            "PUT upload content",
            "POST /api/v2/analyses",
        ],
        confidence_score=0.0,
    )
