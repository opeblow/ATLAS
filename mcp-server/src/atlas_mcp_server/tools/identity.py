"""Identity enforcement inside MCP tools (Sections 5 & 9).

The bearer token is validated at the transport. Here we go one step further
per the spec's "never trust a session id passed as a plain argument": the
caller-supplied `user_id` must match the token's user taken from the actual
HTTP request, otherwise the tool refuses to run.
"""

from __future__ import annotations

from fastmcp.exceptions import ToolError

from atlas_mcp_server.auth.bearer import resolve_user_id
from atlas_mcp_server.config import mcp_settings


def _http_bearer_user() -> str | None:
    try:
        from fastmcp.server.dependencies import get_http_request

        request = get_http_request()
        if request is None:
            return None
        authz = request.headers.get("authorization", "")
        if not authz.lower().startswith("bearer"):
            return None
        token = authz.split(" ", 1)[1].strip()
        return resolve_user_id(token)
    except Exception:
        return None


def enforce_identity(claimed_user_id: str | None) -> None:
    """Raise ToolError if the claimed user_id doesn't match the token's user.

    Only enforced when auth is enabled; without auth (local dev) any user_id is
    accepted so the demo can run unauthenticated.
    """
    if not mcp_settings.require_auth:
        return
    authenticated = _http_bearer_user()
    if authenticated is None:
        raise ToolError("Unauthorized: no valid bearer identity on this request.")
    if claimed_user_id is not None and claimed_user_id != authenticated:
        raise ToolError(
            f"Unauthorized: tool argument user_id={claimed_user_id} "
            f"does not match session identity {authenticated}."
        )