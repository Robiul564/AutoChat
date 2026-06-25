import sys
from pathlib import Path

from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.core.db import Base, engine as app_engine, ensure_runtime_schema, make_engine
from app import models  # noqa: F401 - register ORM tables before create_all()
from app.services.tools import seed_tools


def create_and_seed(url: str) -> None:
    engine = make_engine(url)
    Base.metadata.create_all(bind=engine)
    if engine.url == app_engine.url:
        ensure_runtime_schema()
    session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
    db = session_local()
    try:
        seed_tools(db)
    finally:
        db.close()


def main() -> None:
    tried = []
    candidates = [url for url in [settings.direct_url, settings.database_url] if url]
    for idx, candidate in enumerate(candidates):
        try:
            create_and_seed(candidate)
            source = "DIRECT_URL" if idx == 0 and settings.direct_url else "DATABASE_URL"
            print(f"Database tables are ready via {source}.")
            return
        except OperationalError as exc:
            tried.append(str(exc))
            continue
    if tried:
        raise RuntimeError("Failed to initialize database using DIRECT_URL/DATABASE_URL.\n\n" + "\n\n".join(tried))
    raise RuntimeError("No DATABASE_URL configured.")


if __name__ == "__main__":
    main()
