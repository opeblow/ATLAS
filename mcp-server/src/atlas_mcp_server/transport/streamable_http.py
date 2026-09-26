"""Transport wiring.

FastMCP serves the Streamable HTTP transport (MCP spec 2025-11-25+/2025-03-26)
at the configured path. The returned ASGI app is wrapped with the bearer-token
middleware so every tool call is authenticated before it reaches a tool.
"""

from __future__ import annotations

from atlas_mcp_server.config import mcp_settings


def build_app(mcp: object, middleware_factory) -> object:
    """Return the fully-wrapped ASGI app (Starlette) for uvicorn."""
    # FastMCP exposes both a non-transport ASGI app (http_app) and a run() CLI.
    # We use http_app with the explicit streamable-http transport and mount the
    # bearer middleware outside it, keeping the transport itself unmodified.
    http_app = mcp.http_app(
        path=mcp_settings.streamable_http_path,
        transport="streamable-http",
    )
    return middleware_factory(http_app)