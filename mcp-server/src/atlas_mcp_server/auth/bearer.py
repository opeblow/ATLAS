"""Bearer-token auth for the Streamable HTTP transport (Sections 5 & 9).

Design:
  - Each request must carry a valid, unexpired bearer token bound to a user
    (issued per Alexa+ session via POST /auth/token).
  - This middleware is a *transport gate* only: it validates the token from the
    header without ever consuming the request body, so the Streamable HTTP
    streaming transport works untouched.
  - Claim-level enforcement ("never trust a user_id passed as a plain
    argument") happens inside each tool via `tools.identity.enforce_identity`,
    which checks the caller-supplied user_id against the token's user from the
    actual HTTP request.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from atlas_common.db import SessionLocal
from atlas_common.models import AuthToken

from atlas_mcp_server.config import mcp_settings


def resolve_user_id(token: str | None) -> str | None:
    """Return the user_id bound to a valid, unexpired token."""
    if not token:
        return None
    db = SessionLocal()
    try:
        row = db.query(AuthToken).filter(AuthToken.token == token).first()
        if row is None:
            return None
        if row.expires_at.tzinfo is None:
            expires = row.expires_at.replace(tzinfo=timezone.utc)
        else:
            expires = row.expires_at
        if expires < datetime.now(timezone.utc):
            return None
        return row.user_id
    finally:
        db.close()


def _unauthorized_body() -> bytes:
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32001, "message": "Unauthorized: valid bearer token required."},
        }
    ).encode("utf-8")


async def _reject(send, status: int = 401) -> None:
    payload = _unauthorized_body()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload})


class BearerAuthMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app
        self.require_auth = mcp_settings.require_auth

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path == "/health":
            await self._health(send)
            return

        if not self.require_auth:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        authz = headers.get(b"authorization") or b""
        token = (
            authz.decode("utf-8").split(" ", 1)[1].strip()
            if authz.lower().startswith(b"bearer")
            else None
        )
        if resolve_user_id(token) is None:
            await _reject(send)
            return

        await self.app(scope, receive, send)

    @staticmethod
    async def _health(send) -> None:
        payload = json.dumps({"status": "ok"}).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": payload})