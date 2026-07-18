"""Modal application definition for heavy genomic AST compute.

Deploy with:
    modal deploy modal_app/app.py
"""

from __future__ import annotations

import modal

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("wget", "curl", "ca-certificates", "build-essential")
    .pip_install(
        "fastapi>=0.115.0",
        "uvicorn[standard]>=0.32.0",
        "pydantic>=2.0.0",
        "sqlalchemy>=2.0.0",
        "xgboost>=2.0.0",
        "shap>=0.44.0",
        "numpy>=1.26.0",
        "scikit-learn>=1.4.0",
        "google-genai>=1.0.0",
        "boto3>=1.34.0",
        "httpx>=0.27.0",
    )
)

volume = modal.Volume.from_name("genomic-ast-models", create_if_missing=True)
app = modal.App("genomic-ast", image=image)


@app.function(
    timeout=60 * 60,
    memory=8192,
    cpu=4,
    volumes={"/models": volume},
)
def run_analysis(analysis_id: str, database_url: str, storage_root: str) -> dict:
    import os
    import sys
    from pathlib import Path

    # Make the backend package importable inside the Modal container.
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    os.environ["DATABASE_URL"] = database_url
    os.environ["LOCAL_STORAGE_PATH"] = storage_root
    os.environ["AMRPREDICTOR_MODEL_DIR"] = "/models/amrpredictor"
    os.environ["COMPUTE_BACKEND"] = "local"

    from services.pipeline import run_analysis_job

    run_analysis_job(analysis_id)
    return {"analysis_id": analysis_id, "status": "dispatched"}
