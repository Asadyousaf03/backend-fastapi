from __future__ import annotations

import os


def spawn_analysis(analysis_id: str) -> None:
    """Spawn a Modal remote job when credentials and the app are available."""
    from modal_app.app import run_analysis

    database_url = os.environ["DATABASE_URL"]
    storage_root = os.getenv("LOCAL_STORAGE_PATH", "./data/uploads")
    run_analysis.spawn(analysis_id, database_url, storage_root)
