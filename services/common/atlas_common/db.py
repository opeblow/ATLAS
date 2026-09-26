from __future__ import annotations

from sqlalchemy import create_engine
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


def init_db(create_all: bool = True) -> None:
    """Create tables. Import models first (see atlas_common.models)."""
    from atlas_common import models  # noqa: F401  (registers mappers)

    if create_all:
        Base.metadata.create_all(bind=engine)


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()