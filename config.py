import os
from functools import lru_cache


class Settings:
    def __init__(self) -> None:
        self.app_name = "Hack Nation Genomic AST API"
        self.environment = os.getenv("ENVIRONMENT", "development")
        self.database_url = os.getenv(
            "DATABASE_URL",
            "sqlite:///./data/genomic_ast.db",
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
            "http://localhost:8000",
        )
        self.compute_backend = os.getenv("COMPUTE_BACKEND", "local")
        self.modal_app_name = os.getenv("MODAL_APP_NAME", "genomic-ast")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        self.amrpredictor_model_dir = os.getenv(
            "AMRPREDICTOR_MODEL_DIR",
            "./data/models/amrpredictor",
        )
        self.enable_demo_fallback = os.getenv("ENABLE_DEMO_FALLBACK", "true").lower() in {
            "1",
            "true",
            "yes",
        }
        self.max_upload_bytes = int(os.getenv("MAX_UPLOAD_BYTES", str(5_000_000_000)))


@lru_cache
def get_settings() -> Settings:
    return Settings()
