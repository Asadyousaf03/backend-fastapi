"""Lightweight schema evolution for SQLite/Postgres without full Alembic dependency.

Creates tables and adds missing columns used by the multi-pathogen release.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from db.models import Base


NEW_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "analyses": [
        ("selected_organism_id", "VARCHAR(128)"),
        ("result_schema_version", "VARCHAR(16)"),
        ("remote_job_id", "VARCHAR(128)"),
        ("attempt", "INTEGER DEFAULT 1"),
        ("tool_run_json", "TEXT"),
    ]
}


def migrate_schema(engine: Engine) -> None:
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        for table, columns in NEW_COLUMNS.items():
            existing = _existing_columns(conn, table)
            for name, ddl in columns:
                if name.lower() in existing:
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def _existing_columns(conn, table: str) -> set[str]:
    dialect = conn.engine.dialect.name
    if dialect == "sqlite":
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return {str(row[1]).lower() for row in rows}
    rows = conn.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = :table"
        ),
        {"table": table},
    ).fetchall()
    return {str(row[0]).lower() for row in rows}
