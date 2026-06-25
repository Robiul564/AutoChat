from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy import inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


def normalize_database_url(url: str) -> str:
    url = url.strip().strip('"').strip("'")
    if not url:
        return url
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql+psycopg://"):
        try:
            parts = urlsplit(url)
            query = urlencode([(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != "pgbouncer"])
            url = urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))
        except ValueError:
            # Keep the original URL if parsing fails (for example unresolved placeholder text).
            return url
    return url


def make_engine(url: str) -> Engine:
    database_url = normalize_database_url(url)
    if database_url.startswith("sqlite:///"):
        db_path = database_url.replace("sqlite:///", "", 1)
        if db_path not in (":memory:", ""):
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args, future=True)


database_url = normalize_database_url(settings.database_url)
engine = make_engine(database_url)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_runtime_schema() -> None:
    inspector = inspect(engine)
    if "ai_settings" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("ai_settings")}
        if "workflow_config_json" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE ai_settings ADD COLUMN workflow_config_json JSON DEFAULT '{}' NOT NULL"))
