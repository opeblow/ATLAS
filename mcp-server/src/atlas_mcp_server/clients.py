"""HTTP clients to the finance + scheduling services.

The MCP server is a thin, stateless HTTP layer: it never touches the database
or the model directly. Tools forward structured calls and pass back structured
output (Section 4 architecture).

Both a sync and an async client are exposed. Use the async ones from async tool
handlers: on the single-origin deploy (Render) these services live in the *same*
process, so a blocking `httpx.post` would stall the event loop that has to
serve the very request being made, and the call would only ever fail on timeout.
"""

from __future__ import annotations

from typing import Any

import httpx

from atlas_common.auth import current_bearer
from atlas_mcp_server.config import mcp_settings

_TIMEOUT = httpx.Timeout(15.0)


def _headers() -> dict[str, str]:
    token = current_bearer.get()
    return {"Authorization": f"Bearer {token}"} if token else {}


def _post(base: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    r = httpx.post(f"{base}{path}", json=payload, headers=_headers(), timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _get(base: str, path: str, **params: Any) -> dict[str, Any]:
    r = httpx.get(f"{base}{path}", params=params, headers=_headers(), timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()


async def _post_async(base: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.post(f"{base}{path}", json=payload, headers=_headers())
    r.raise_for_status()
    return r.json()


async def _get_async(base: str, path: str, **params: Any) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.get(f"{base}{path}", params=params, headers=_headers())
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


async def finance_post_async(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    return await _post_async(mcp_settings.finance_url, path, payload)


async def scheduling_post_async(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    return await _post_async(mcp_settings.scheduling_url, path, payload)


async def finance_get_async(path: str, **params: Any) -> dict[str, Any]:
    return await _get_async(mcp_settings.finance_url, path, **params)


async def scheduling_get_async(path: str, **params: Any) -> dict[str, Any]:
    return await _get_async(mcp_settings.scheduling_url, path, **params)