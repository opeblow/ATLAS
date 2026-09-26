"""ATLAS MCP server entry point.

Assembles the stateless FastMCP server with the six tools and serves Streamable
HTTP (spec 2025-11-25+) behind bearer auth. Run:

    uvicorn atlas_mcp_server.server:app --port 8003
    # or
    python -m atlas_mcp_server

The server holds no in-memory session state and never loads the risk model
(Sections 4, 8.1): every request carries its token + user_id and hits the
finance/scheduling services over HTTP.
"""

from __future__ import annotations

import fastmcp
from fastmcp import FastMCP

from atlas_common.db import init_db

from atlas_mcp_server.auth.bearer import BearerAuthMiddleware
from atlas_mcp_server.config import mcp_settings
from atlas_mcp_server.tools import register
from atlas_mcp_server.transport.streamable_http import build_app

init_db()

mcp = FastMCP(
    mcp_settings.name,
    instructions="ATLAS — agentic chief of staff. Money + time, one voice.",
    version=mcp_settings.version,
)

register(mcp)

app = build_app(mcp, BearerAuthMiddleware)


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8003, log_level="info")


if __name__ == "__main__":
    main()