import os
from functools import lru_cache

from dotenv import load_dotenv


load_dotenv()


def normalize_database_url(url: str) -> str:
    """Accept Supabase/Neon postgres URLs and force the psycopg3 dialect."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


class Settings:
    def __init__(self) -> None:
        self.app_name = "Hack Nation Genomic AST API"
        self.environment = os.getenv("ENVIRONMENT", "development")
        self.database_url = normalize_database_url(
            os.getenv(
                "DATABASE_URL",
                "sqlite:///./data/genomic_ast.db",
            )
        )
        self.storage_backend = os.getenv("STORAGE_BACKEND", "local")
        self.local_storage_path = os.getenv("LOCAL_STORAGE_PATH", "./data/uploads")
        self.s3_endpoint_url = os.getenv("S3_ENDPOINT_URL")
        self.s3_bucket = os.getenv("S3_BUCKET", "genomic-ast")
        self.s3_access_key = os.getenv("S3_ACCESS_KEY")
        self.s3_secret_key = os.getenv("S3_SECRET_KEY")
        self.s3_region = os.getenv("S3_REGION", "us-east-1")
        self.public_api_base = os.getenv(
            "PUBLIC_API_BASE",
            "http://localhost:8001",
        )
        self.compute_backend = os.getenv("COMPUTE_BACKEND", "local")
        self.modal_app_name = os.getenv("MODAL_APP_NAME", "genomic-ast")
        self.google_cloud_project = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.google_cloud_region = os.getenv("GOOGLE_CLOUD_REGION", "us-central1")
        self.cloud_run_job_name = os.getenv(
            "CLOUD_RUN_JOB_NAME",
            "genomic-ast-worker",
        )
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        self.amrpredictor_model_dir = os.getenv(
            "AMRPREDICTOR_MODEL_DIR",
            "./data/models/amrpredictor",
        )
        # Legacy flag retained for docs compatibility; production scientific path
        # no longer uses heuristic demo predictions.
        self.enable_demo_fallback = os.getenv("ENABLE_DEMO_FALLBACK", "false").lower() in {
            "1",
            "true",
            "yes",
        }
        self.require_real_tools = os.getenv("REQUIRE_REAL_TOOLS", "true").lower() in {
            "1",
            "true",
            "yes",
        }
        # real | fixture  (fixture is for CI/golden tests only)
        self.tool_execution_mode = os.getenv("TOOL_EXECUTION_MODE", "real").lower()
        self.allow_fixture_mode = os.getenv("ALLOW_FIXTURE_MODE", "false").lower() in {
            "1",
            "true",
            "yes",
        }
        self.fixture_dir = os.getenv("FIXTURE_DIR", "./tests/fixtures/tools")
        self.resfinder_db = os.getenv("RESFINDER_DB", "/opt/dbs/resfinder_db")
        self.pointfinder_db = os.getenv("POINTFINDER_DB", "/opt/dbs/pointfinder_db")
        self.amrfinder_db = os.getenv(
            "AMRFINDER_DB",
            "/opt/dbs/amrfinder/2026-05-15.1",
        )
        self.tool_timeout_seconds = int(os.getenv("TOOL_TIMEOUT_SECONDS", "1800"))
        self.amrfinder_threads = int(os.getenv("AMRFINDER_THREADS", "4"))
        self.max_upload_bytes = int(os.getenv("MAX_UPLOAD_BYTES", str(100_000_000)))


@lru_cache
def get_settings() -> Settings:
    return Settings()
