"""HTTP clients to the finance + scheduling services.

The MCP server is a thin, stateless HTTP layer: it never touches the database
or the model directly. Tools forward structured calls and pass back structured
output (Section 4 architecture).
"""

from __future__ import annotations

from typing import Any

import httpx

from atlas_mcp_server.config import mcp_settings

_TIMEOUT = httpx.Timeout(15.0)


def _post(base: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    r = httpx.post(f"{base}{path}", json=payload, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _get(base: str, path: str, **params: Any) -> dict[str, Any]:
    r = httpx.get(f"{base}{path}", params=params, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()


def finance_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _post(mcp_settings.finance_url, path, payload)


def scheduling_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _post(mcp_settings.scheduling_url, path, payload)


def finance_get(path: str, **params: Any) -> dict[str, Any]:
    return _get(mcp_settings.finance_url, path, **params)


def scheduling_get(path: str, **params: Any) -> dict[str, Any]:
    return _get(mcp_settings.scheduling_url, path, **params)