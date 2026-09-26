from __future__ import annotations

import os

from atlas_common.config import settings as common


class McpSettings:
    name: str = "atlas"
    version: str = "0.1.0"
    # Streamable HTTP endpoint (MCP spec 2025-11-25+).
    streamable_http_path: str = os.getenv("ATLAS_MCP_PATH", "/mcp")

    # Bearer auth (Section 5/9): short-lived per-session tokens are validated on
    # every request against auth_tokens, and each tool-call's user_id must match
    # the token's user. Set ATLAS_REQUIRE_AUTH=0 for local dev only.
    require_auth: bool = common.require_auth

    finance_url: str = common.finance_url
    scheduling_url: str = common.scheduling_url


mcp_settings = McpSettings()