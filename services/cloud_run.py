from __future__ import annotations

import google.auth
from google.auth.transport.requests import AuthorizedSession

from config import get_settings


def execute_analysis_job(analysis_id: str) -> str:
    """Start one Cloud Run Job execution with an analysis ID override."""
    settings = get_settings()
    if not settings.google_cloud_project:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT is required for Cloud Run dispatch")

    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    session = AuthorizedSession(credentials)
    job_path = (
        f"projects/{settings.google_cloud_project}"
        f"/locations/{settings.google_cloud_region}"
        f"/jobs/{settings.cloud_run_job_name}"
    )
    response = session.post(
        f"https://run.googleapis.com/v2/{job_path}:run",
        json={
            "overrides": {
                "containerOverrides": [
                    {
                        "name": "worker",
                        "env": [{"name": "ANALYSIS_ID", "value": analysis_id}],
                    }
                ]
            }
        },
        timeout=30,
    )
    if not response.ok:
        raise RuntimeError(
            f"Cloud Run dispatch failed ({response.status_code}): {response.text}"
        )
    payload = response.json()
    return str(payload.get("name") or f"cloud-run:{analysis_id}")
