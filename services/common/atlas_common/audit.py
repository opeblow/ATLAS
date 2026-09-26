"""Audit logging helper for MCP tool calls (Section 8.6).

Every MCP invocation is written to mcp_tool_calls — append-only, insert-only.
In production this row doubles as the security / anomaly-detection log.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator

from atlas_common.db import SessionLocal
from atlas_common.models import McpToolCall


def log_mcp_call(
    *,
    user_id: str,
    tool_name: str,
    input: dict[str, Any] | None = None,
    output: dict[str, Any] | None = None,
    latency_ms: int = 0,
    error: str | None = None,
) -> None:
    """Best-effort write; never let audit logging break the request path."""
    try:
        db = SessionLocal()
        try:
            db.add(
                McpToolCall(
                    user_id=user_id,
                    tool_name=tool_name,
                    input=input,
                    output=output,
                    latency_ms=latency_ms,
                    error=error,
                )
            )
            db.commit()
        finally:
            db.close()
    except Exception:  # pragma: no cover
        pass


@contextmanager
def timed_tool_call(user_id: str, tool_name: str, input: dict[str, Any] | None) -> Iterator[None]:
    """Capture latency + outcome of one tool invocation, then log it."""
    start = time.perf_counter()
    try:
        yield
        log_mcp_call(
            user_id=user_id,
            tool_name=tool_name,
            input=input,
            latency_ms=int((time.perf_counter() - start) * 1000),
        )
    except Exception as exc:
        log_mcp_call(
            user_id=user_id,
            tool_name=tool_name,
            input=input,
            latency_ms=int((time.perf_counter() - start) * 1000),
            error=str(exc),
        )
        raise