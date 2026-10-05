"""Cognito bearer-token validation shared by ATLAS HTTP services."""

from __future__ import annotations

import contextvars
import hashlib
import os
from functools import lru_cache
from hmac import compare_digest
from typing import Any

import jwt
from fastapi import HTTPException, Request
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError
from sqlalchemy.exc import SQLAlchemyError

from atlas_common.config import settings

current_bearer: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "atlas_current_bearer", default=None
)


@lru_cache(maxsize=4)
def _jwks_client(issuer: str) -> PyJWKClient:
    return PyJWKClient(f"{issuer}/.well-known/jwks.json", timeout=5)


def cognito_issuer() -> str:
    issuer = os.getenv("ATLAS_COGNITO_ISSUER")
    if issuer:
        return issuer.rstrip("/")
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    pool_id = os.getenv("ATLAS_COGNITO_USER_POOL_ID")
    if not region or not pool_id:
        raise ValueError("Cognito issuer or user pool configuration is missing")
    return f"https://cognito-idp.{region}.amazonaws.com/{pool_id}"


def token_digest(token: str) -> str:
    """Keyed-free SHA-256 of a bearer token, for storage and constant-time lookup.

    Dev tokens are stored so a database dump does not hand out live credentials.
    Equality is still checked with compare_digest over the hex digest so the
    comparison does not leak the stored value's prefix through timing.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_bearer(token: str) -> dict[str, Any]:
    """Validate a Cognito access token or explicitly enabled local dev token."""
    if settings.auth_mode == "dev":
        from datetime import datetime, timezone

        from atlas_common.db import SessionLocal
        from atlas_common.models import AuthToken

        digest = token_digest(token)
        db = SessionLocal()
        try:
            row = db.query(AuthToken).filter(AuthToken.token == digest).first()
            if row is None:
                # Rows minted before digests were introduced store the bearer
                # value itself, so a digest-only lookup would silently log every
                # existing session out. Fall back to the raw value once, then
                # rewrite the row to its digest so plaintext at rest drains away
                # as users come back rather than needing a migration script.
                row = db.query(AuthToken).filter(AuthToken.token == token).first()
                if row is not None:
                    row.token = digest
                    try:
                        db.commit()
                    except SQLAlchemyError:
                        # Re-hashing is best-effort; the token is still valid.
                        db.rollback()
            if row is None:
                # Compare against a dummy so a missing row and a wrong token cost
                # the same, then fail identically.
                compare_digest(digest, token_digest("absent"))
                raise ValueError("invalid token")
            expires = row.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires <= datetime.now(timezone.utc):
                raise ValueError("expired token")
            return {"sub": row.user_id, "token_use": "dev"}
        finally:
            db.close()

    issuer = cognito_issuer()
    key = _jwks_client(issuer).get_signing_key_from_jwt(token).key
    claims = jwt.decode(
        token,
        key,
        algorithms=["RS256"],
        issuer=issuer,
        options={"verify_aud": False},
        leeway=30,
    )
    if claims.get("token_use") != "access":
        raise ValueError("Cognito access token required")
    client_id = os.getenv("ATLAS_COGNITO_APP_CLIENT_ID")
    if not client_id or claims.get("client_id") != client_id:
        raise ValueError("token is not issued to the configured app client")
    if not isinstance(claims.get("sub"), str) or not claims["sub"]:
        raise ValueError("token subject is missing")
    return claims


def resolve_bearer_user_id(token: str | None) -> str | None:
    """Best-effort subject for an untrusted bearer token, or None.

    Used by middleware that needs a rate-limit key before the route has run, so
    it must never raise. SQLAlchemyError is caught because in dev mode this hits
    the database: an unreachable Postgres has to degrade to "anonymous", not turn
    every request (including /health) into a 500.
    """
    if not token:
        return None
    try:
        return str(verify_bearer(token)["sub"])
    except (ValueError, jwt.PyJWTError, PyJWKClientError, OSError, SQLAlchemyError):
        return None


def authenticated_user(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if settings.auth_mode == "dev" and not settings.require_auth:
        request.state.authenticated_user_id = "__local_dev__"
        return "__local_dev__"
    if scheme.lower() != "bearer" or not separator or not token.strip():
        raise HTTPException(status_code=401, detail="Bearer authentication required")
    try:
        claims = verify_bearer(token.strip())
    except (ValueError, jwt.PyJWTError, PyJWKClientError, OSError) as exc:
        raise HTTPException(status_code=401, detail="Invalid bearer token") from exc
    request.state.authenticated_user_id = claims["sub"]
    return str(claims["sub"])


def require_user_id(claimed_user_id: str, authenticated_user_id: str) -> None:
    if settings.auth_mode == "dev" and not settings.require_auth:
        return
    if claimed_user_id != authenticated_user_id:
        raise HTTPException(status_code=403, detail="User identity does not match token")
