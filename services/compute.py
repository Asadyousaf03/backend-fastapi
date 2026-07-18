from __future__ import annotations

import threading

from config import get_settings
from services.pipeline import run_analysis_job


def dispatch_analysis(analysis_id: str) -> None:
    settings = get_settings()
    if settings.compute_backend == "modal":
        try:
            from modal_app.runner import spawn_analysis

            spawn_analysis(analysis_id)
            return
        except Exception:
            # Fall through to local execution if Modal is not configured.
            pass

    thread = threading.Thread(target=run_analysis_job, args=(analysis_id,), daemon=True)
    thread.start()
