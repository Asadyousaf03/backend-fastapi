from __future__ import annotations

from config import get_settings


def spawn_analysis(analysis_id: str) -> str:
    """Spawn a Modal job. Raises on failure (no silent local fallback)."""
    settings = get_settings()
    try:
        from modal_app.app import app, run_analysis
    except Exception as exc:
        raise RuntimeError(
            "Modal app could not be imported. Deploy modal_app/app.py and configure secrets."
        ) from exc

    try:
        # Prefer explicit deployed lookup when available.
        call = run_analysis.spawn(analysis_id)
        remote_id = getattr(call, "object_id", None) or getattr(call, "function_call_id", None)
        return str(remote_id or f"modal:{settings.modal_app_name}:{analysis_id}")
    except Exception as exc:
        raise RuntimeError(f"Modal dispatch failed for analysis {analysis_id}: {exc}") from exc
