from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config import get_settings
from db.migrate import migrate_schema

settings = get_settings()

connect_args: dict = {}
if settings.database_url.startswith("sqlite"):
    Path("./data").mkdir(parents=True, exist_ok=True)
    connect_args = {"check_same_thread": False}
elif settings.database_url.startswith("postgresql"):
    # Supabase transaction pooler (port 6543) does not support prepared statements.
    connect_args = {"prepare_threshold": None}

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db() -> None:
    migrate_schema(engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
