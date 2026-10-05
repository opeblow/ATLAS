from __future__ import annotations

import pytest
from sqlalchemy.exc import OperationalError

from atlas_common import auth


class _UnreachableDB:
    """Stands in for a Session whose connection fails, as it would when Postgres is
    unreachable. Shaped to match verify_bearer, which calls SessionLocal() then
    .query() directly (no context manager) and always .close()s in a finally.

    The error type matters: resolve_bearer_user_id is expected to swallow
    SQLAlchemyError specifically, not arbitrary exceptions.
    """

    def query(self, *_args, **_kwargs):
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    def close(self):
        pass


def test_token_digest_is_stable_and_not_the_token():
    token = "atlas_dev_live_secret_value"

    digest = auth.token_digest(token)

    assert digest == auth.token_digest(token)
    assert digest != token
    assert len(digest) == 64  # sha256 hex


def test_token_digest_separates_near_identical_tokens():
    assert auth.token_digest("abc") != auth.token_digest("abd")


def test_resolve_bearer_user_id_never_raises(monkeypatch):
    """Middleware calls this on untrusted input before routing. It must return a
    subject or None -- never propagate -- or a bad token breaks every route."""
    from atlas_common.config import settings

    monkeypatch.setattr(settings, "auth_mode", "cognito")
    # Force the "no pool configured" path so this stays offline and deterministic
    # regardless of the ambient AWS environment.
    monkeypatch.delenv("ATLAS_COGNITO_USER_POOL_ID", raising=False)
    monkeypatch.delenv("ATLAS_COGNITO_REGION", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)

    assert auth.resolve_bearer_user_id(None) is None
    assert auth.resolve_bearer_user_id("") is None
    assert auth.resolve_bearer_user_id("garbage") is None
    assert auth.resolve_bearer_user_id("a.b.c") is None


def test_verify_bearer_propagates_db_failure(monkeypatch):
    """A token cannot be validated without the store, so verify_bearer must raise
    rather than treat an unreachable database as 'invalid token'."""
    from atlas_common.config import settings

    monkeypatch.setattr(settings, "auth_mode", "dev")
    monkeypatch.setattr("atlas_common.db.SessionLocal", _UnreachableDB)

    with pytest.raises(OperationalError):
        auth.verify_bearer("some-token")


def test_resolve_bearer_user_id_degrades_to_none_when_the_db_is_down(monkeypatch):
    """An unreachable Postgres must degrade to 'anonymous', not turn /health into
    a 500: edge middleware calls this ahead of routing, on every request."""
    from atlas_common.config import settings

    monkeypatch.setattr(settings, "auth_mode", "dev")
    monkeypatch.setattr("atlas_common.db.SessionLocal", _UnreachableDB)

    assert auth.resolve_bearer_user_id("some-token") is None


@pytest.fixture
def dev_store(monkeypatch):
    """A real in-memory SQLite AuthToken table, wired in as the session factory."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from atlas_common.config import settings
    from atlas_common.models import AuthToken

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    AuthToken.__table__.create(engine)
    session = sessionmaker(bind=engine)()

    monkeypatch.setattr(settings, "auth_mode", "dev")

    # verify_bearer calls SessionLocal() and then closes what it gets, so the
    # patch target has to be a factory, not the session itself.
    monkeypatch.setattr("atlas_common.db.SessionLocal", lambda: session)

    return session, AuthToken


def _insert(session, model, token_value, user_id="u_1", ttl_hours=1):
    from datetime import datetime, timedelta, timezone

    row = model(
        token=token_value,
        user_id=user_id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=ttl_hours),
    )
    session.add(row)
    session.commit()
    return row


def test_dev_token_validates_from_its_digest(dev_store):
    session, model = dev_store
    _insert(session, model, auth.token_digest("live-token"))

    assert auth.verify_bearer("live-token") == {"sub": "u_1", "token_use": "dev"}


def test_wrong_token_is_rejected(dev_store):
    session, model = dev_store
    _insert(session, model, auth.token_digest("live-token"))

    with pytest.raises(ValueError):
        auth.verify_bearer("some-other-token")


def test_expired_token_is_rejected(dev_store):
    session, model = dev_store
    _insert(session, model, auth.token_digest("stale"), ttl_hours=-1)

    with pytest.raises(ValueError):
        auth.verify_bearer("stale")


def test_legacy_plaintext_row_still_authenticates_then_gets_rehashed(dev_store):
    """Rows minted before digests stored the bearer value. They must keep working,
    and be rewritten to a digest so plaintext at rest drains away on its own."""
    session, model = dev_store
    _insert(session, model, "legacy-plaintext-token")

    claims = auth.verify_bearer("legacy-plaintext-token")

    assert claims["sub"] == "u_1"
    session.expire_all()
    stored = session.query(model).one().token
    assert stored == auth.token_digest("legacy-plaintext-token")
    assert stored != "legacy-plaintext-token"