from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from atlas_common.auth import authenticated_user
from atlas_common.db import Base, get_session
from atlas_common.models import ScheduleBlock, User
from app.main import app


def test_schedule_update_requires_auth_and_enforces_block_ownership():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with sessions() as db:
        db.add_all(
            [
                User(id="owner", alexa_account_id="alexa::owner"),
                User(id="attacker", alexa_account_id="alexa::attacker"),
            ]
        )
        db.add(
            ScheduleBlock(
                id="private-block",
                user_id="owner",
                title="Private block",
                start_at=datetime(2026, 10, 4, 9, tzinfo=timezone.utc),
                end_at=datetime(2026, 10, 4, 10, tzinfo=timezone.utc),
                status="committed",
            )
        )
        db.commit()

    def session_override():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_session] = session_override
    try:
        with TestClient(app) as client:
            unauthenticated = client.patch(
                "/schedule/block/private-block", params={"status": "completed"}
            )
            assert unauthenticated.status_code == 401, unauthenticated.text

            app.dependency_overrides[authenticated_user] = lambda: "attacker"
            forbidden = client.patch(
                "/schedule/block/private-block", params={"status": "completed"}
            )
            assert forbidden.status_code == 404

            app.dependency_overrides[authenticated_user] = lambda: "owner"
            updated = client.patch(
                "/schedule/block/private-block", params={"status": "completed"}
            )
            assert updated.status_code == 200
            assert updated.json()["status"] == "completed"

            invalid = client.patch(
                "/schedule/block/private-block", params={"status": "admin"}
            )
            assert invalid.status_code == 422
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
