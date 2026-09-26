from __future__ import annotations

import time

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from atlas_common.config import settings


class Base(DeclarativeBase):
    pass


def _engine_kwargs() -> dict:
    if settings.db_url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {
        "pool_size": 25,
        "max_overflow": 50,
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    }


engine = create_engine(settings.db_url, echo=settings.echo_sql, **_engine_kwargs())

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(create_all: bool = True, attempts: int = 3) -> None:
    """Create tables. Import models first (see atlas_common.models).

    Every service calls this at import time and in development they share one
    SQLite file, so two processes can both pass create_all's checkfirst probe and
    race to CREATE the same table. The loser retries, by which point the table
    exists and checkfirst skips it. Postgres is serialised by DDL locks, so this
    only ever fires on SQLite.
    """
    from atlas_common import models  # noqa: F401  (registers mappers)

    if not create_all:
        return

    for attempt in range(attempts):
        try:
            Base.metadata.create_all(bind=engine)
            return
        except OperationalError as exc:
            concurrent = "already exists" in str(exc).lower()
            if not concurrent or attempt == attempts - 1:
                raise
            time.sleep(0.2 * (attempt + 1))


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()