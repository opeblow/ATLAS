"""Drive the ATLAS voice-intent loop against a running local edge gateway."""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client


async def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    base_url = os.getenv("ATLAS_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    mcp_url = os.getenv("ATLAS_MCP_URL", f"{base_url}/mcp/mcp")
    user_id = "u_demo"
    headers: dict[str, str] = {}
    health = httpx.get(f"{base_url}/mcp/health", timeout=10)
    health.raise_for_status()
    auth_probe = httpx.post(mcp_url, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, timeout=10)
    if auth_probe.status_code == 401:
        token = httpx.post(f"{base_url}/finance/auth/token", json={"user_id": user_id}, timeout=10)
        token.raise_for_status()
        headers["Authorization"] = f"Bearer {token.json()['token']}"

    now = datetime.now(timezone.utc)
    run_id = uuid.uuid4().hex
    deadlines = [{
        "title": "AI Systems Assignment",
        "due_at": (now + timedelta(days=6)).isoformat(),
        "weight": 2.0,
    }, {
        "title": "Math Midterm",
        "due_at": (now + timedelta(days=5)).isoformat(),
        "weight": 1.5,
    }]
    availability = [{
        "date": (now + timedelta(days=day)).date().isoformat(),
        "start_hour": 18,
        "end_hour": 21,
    } for day in range(1, 6)]

    async with streamable_http_client(
        mcp_url, http_client=create_mcp_http_client(headers=headers)
    ) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()

            async def call(name: str, args: dict) -> str:
                result = await session.call_tool(name, args)
                text = "".join(item.text or "" for item in result.content if getattr(item, "type", None) == "text")
                if result.is_error:
                    raise RuntimeError(f"{name} failed: {text}")
                print(f"\n[{name}]\n{text}")
                return text

            await call("assess_affordability", {"user_id": user_id, "amount_ngn": 120000, "category": "electronics"})
            await call("get_risk_snapshot", {"user_id": user_id, "window": "30d"})
            transaction = {
                "user_id": user_id,
                "amount_ngn": -45000,
                "category": "food",
                "idempotency_key": f"atlas-demo-log-{run_id}",
            }
            await call("log_transaction", transaction)
            await call("log_transaction", transaction)
            await call("plan_study_week", {"user_id": user_id, "deadlines": deadlines, "available_hours": availability})

            async with httpx.AsyncClient(timeout=30) as client:
                plan = await client.post(f"{base_url}/schedule/plan/week", json={
                    "user_id": user_id,
                    "deadlines": deadlines,
                    "available_hours": availability,
                })
                plan.raise_for_status()
                blocks = plan.json().get("proposed_blocks", [])
            commit = {
                "user_id": user_id,
                "blocks": blocks,
                "idempotency_key": f"atlas-demo-plan-{run_id}",
            }
            await call("commit_schedule", commit)
            await call("commit_schedule", commit)
            await call("get_daily_brief", {"user_id": user_id})

if __name__ == "__main__":
    asyncio.run(main())