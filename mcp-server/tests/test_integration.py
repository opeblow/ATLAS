"""End-to-end tests against a running ATLAS stack.

Skips (not fails) when the MCP server is not reachable — run the stack first.
Two supported layouts, both driven by env vars:

    # single-origin gateway (what Render runs)
    ATLAS_BASE_URL=http://127.0.0.1:8000 python -m atlas_edge.asgi

    # four separate processes (local dev)
    uvicorn app.main:app --port 8001            # in services/finance-service
    uvicorn app.main:app --port 8002            # in services/scheduling-service
    uvicorn atlas_mcp_server.server:app --port 8003

Then:  pytest tests/test_integration.py -s
"""

from __future__ import annotations

import os
import uuid

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

# Set ATLAS_BASE_URL to point the whole suite at a single-origin gateway. Left
# unset, it falls back to the separate dev ports.
BASE_URL = os.getenv("ATLAS_BASE_URL", "").rstrip("/")
if BASE_URL:
    MCP_URL = os.getenv("ATLAS_MCP_URL", f"{BASE_URL}/mcp/mcp")
    FINANCE_URL = f"{BASE_URL}/finance"
else:
    MCP_URL = "http://127.0.0.1:8003/mcp"
    FINANCE_URL = "http://127.0.0.1:8001"

TEST_USER_ID = f"atlas-integration-{uuid.uuid4().hex}"


def _server_up() -> bool:
    try:
        health = f"{BASE_URL}/mcp/health" if BASE_URL else "http://127.0.0.1:8003/health"
        return httpx.get(health, timeout=5).status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _server_up(), reason="ATLAS MCP server not running")


def _auth_enforced() -> bool:
    try:
        r = httpx.post(MCP_URL, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, timeout=5)
        return r.status_code == 401
    except Exception:
        return False


def _token() -> str:
    r = httpx.post(
        f"{FINANCE_URL}/auth/token", json={"user_id": TEST_USER_ID}, timeout=10
    )
    r.raise_for_status()
    return r.json()["token"]


def test_rest_auth_blocks_anonymous_and_cross_user_access():
    if not _auth_enforced():
        pytest.skip("run with bearer auth enabled to test REST authorization")
    token = _token()
    headers = {"Authorization": f"Bearer {token}"}
    own = httpx.get(
        f"{FINANCE_URL}/users/{TEST_USER_ID}/balance", headers=headers, timeout=10
    )
    other = httpx.get(
        f"{FINANCE_URL}/users/not-the-authenticated-user/balance",
        headers=headers,
        timeout=10,
    )
    anonymous = httpx.get(
        f"{FINANCE_URL}/users/{TEST_USER_ID}/balance", timeout=10
    )
    assert own.status_code == 200
    assert other.status_code == 403
    assert anonymous.status_code == 401


async def _call_tool(session: ClientSession, name: str, args: dict) -> str:
    res = await session.call_tool(name, args)
    text = "".join(c.text or "" for c in res.content if getattr(c, "type") == "text")
    assert not res.is_error, f"tool {name} failed: {text}"
    return text


async def _do_tool_calls() -> None:
    headers: dict[str, str] = {}
    if _auth_enforced():
        headers["Authorization"] = f"Bearer {_token()}"
    http = create_mcp_http_client(headers=headers    )
    async with streamable_http_client(MCP_URL, http_client=http) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            initialized = await session.initialize()
            assert initialized.protocol_version >= "2025-11-25", (
                f"MCP protocol {initialized.protocol_version} is older than required"
            )
            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            assert {
                "assess_affordability",
                "get_risk_snapshot",
                "log_transaction",
                "plan_study_week",
                "commit_schedule",
                "get_daily_brief",
            } <= names, f"missing tools: {names}"

            # 1. can I afford this?
            afford = await _call_tool(
                session,
                "assess_affordability",
                {
                    "user_id": TEST_USER_ID,
                    "amount_ngn": 45000,
                    "category": "electronics",
                },
            )
            assert "Verdict:" in afford

            # 2. risk snapshot, explainable
            risk = await _call_tool(
                session,
                "get_risk_snapshot",
                {"user_id": TEST_USER_ID, "window": "30d"},
            )
            assert "risk level" in risk.lower()

            # 3. log a transaction and prove a retry is deduplicated
            transaction_key = f"integration-{uuid.uuid4().hex}"
            transaction_args = {
                "user_id": TEST_USER_ID,
                "amount_ngn": -1250,
                "category": "integration-test",
                "idempotency_key": transaction_key,
            }
            logged = await _call_tool(session, "log_transaction", transaction_args)
            assert "Logged." in logged
            duplicate_transaction = await _call_tool(
                session, "log_transaction", transaction_args
            )
            assert "Duplicate" in duplicate_transaction

            # 4. plan a study week (real scheduling service)
            from datetime import datetime, timedelta, timezone

            now = datetime.now(timezone.utc)
            availability = [
                {
                    "date": (now + timedelta(days=k)).date().isoformat(),
                    "start_hour": 9,
                    "end_hour": 12,
                }
                for k in range(1, 4)
            ]
            deadlines = [
                {
                    "title": "TDD Exam",
                    "due_at": (now + timedelta(days=3)).isoformat(),
                    "weight": 2.0,
                }
            ]
            plan = await _call_tool(
                session,
                "plan_study_week",
                {
                    "user_id": TEST_USER_ID,
                    "deadlines": deadlines,
                    "available_hours": availability,
                },
            )
            assert "Proposed" in plan

            # 5. commit a block and prove a retry cannot book it twice
            commit_key = f"integration-{uuid.uuid4().hex}"
            start_at = (now + timedelta(days=180)).replace(
                minute=0, second=0, microsecond=0
            )
            commit_args = {
                "user_id": TEST_USER_ID,
                "idempotency_key": commit_key,
                "blocks": [
                    {
                        "title": "ATLAS integration test",
                        "start_at": start_at.isoformat(),
                        "end_at": (start_at + timedelta(hours=1)).isoformat(),
                    }
                ],
            }
            committed = await _call_tool(session, "commit_schedule", commit_args)
            assert "1 block(s) added" in committed
            duplicate_commit = await _call_tool(
                session, "commit_schedule", commit_args
            )
            assert "already committed" in duplicate_commit.lower()

            if _auth_enforced():
                spoof = await session.call_tool(
                    "get_risk_snapshot",
                    {"user_id": "u_attacker", "window": "30d"},
                )
                assert spoof.is_error, "user_id claim enforcement must reject mismatches"

            # 6. daily brief composes money + time
            brief = await _call_tool(
                session, "get_daily_brief", {"user_id": TEST_USER_ID}
            )
            assert "Good morning" in brief or "balance" in brief


@pytest.mark.asyncio
async def test_full_loop():
    await _do_tool_calls()


@pytest.mark.asyncio
@pytest.mark.skipif(not _auth_enforced(), reason="run with ATLAS_REQUIRE_AUTH=1 to test auth")
async def test_auth_required():
    # A direct JSON-RPC probe without a token must be refused when auth is on.
    r = httpx.post(MCP_URL, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, timeout=10)
    assert r.status_code == 401
    assert r.headers.get("content-type", "").startswith("application/json")