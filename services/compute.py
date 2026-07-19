from __future__ import annotations

import threading

from config import get_settings
from services.pipeline import run_analysis_job


def dispatch_analysis(analysis_id: str) -> str | None:
    """Dispatch analysis. Returns remote job id when Modal is used.

    Fail closed for Modal: no silent local fallback.
    """
    settings = get_settings()
    if settings.compute_backend == "modal":
        from modal_app.runner import spawn_analysis

        remote_id = spawn_analysis(analysis_id)
        return remote_id

    if settings.compute_backend == "cloud_run":
        from services.cloud_run import execute_analysis_job

        return execute_analysis_job(analysis_id)

    if settings.compute_backend != "local":
        raise RuntimeError(f"Unsupported COMPUTE_BACKEND={settings.compute_backend}")

    thread = threading.Thread(target=run_analysis_job, args=(analysis_id,), daemon=True)
    thread.start()
    return None
