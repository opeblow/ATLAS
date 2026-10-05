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
from typing import Any

from atlas_common.auth import current_bearer, resolve_bearer_user_id

from atlas_mcp_server.config import mcp_settings


def resolve_user_id(token: str | None) -> str | None:
    """Return the subject bound to a valid Cognito or development token."""
    return resolve_bearer_user_id(token)


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
        parts = authz.decode("utf-8", errors="ignore").split(" ", 1)
        token = parts[1].strip() if len(parts) == 2 and parts[0].lower() == "bearer" else None
        authenticated_user_id = resolve_user_id(token)
        if authenticated_user_id is None:
            await _reject(send)
            return

        context_token = current_bearer.set(token)
        scope = {**scope, "state": {**scope.get("state", {}), "authenticated_user_id": authenticated_user_id}}
        try:
            await self.app(scope, receive, send)
        finally:
            current_bearer.reset(context_token)

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