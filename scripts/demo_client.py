"""ATLAS live demo client — a minimal MCP client for the 7-minute script.

Connects to the self-hosted Streamable HTTP MCP server on :8003, lists the
six tools, then walks the demo narrative: risk snapshot, affordability,
idempotent log, study plan, commit, and the daily brief.

Usage:
    python scripts/demo_client.py                 # auth-off server
    $env:ATLAS_TOKEN = "..."; python scripts/demo_client.py   # auth-on server
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from mcp import ClientSession
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

URL = os.getenv("ATLAS_MCP_URL", "http://127.0.0.1:8003/mcp")
USER = "u_demo"


def _headers() -> dict[str, str]:
    if token := os.getenv("ATLAS_TOKEN"):
        return {"Authorization": f"Bearer {token}"}
    return {}


async def _call(session: ClientSession, tool: str, args: dict) -> None:
    try:
        result = await session.call_tool(tool, args)
        text = result.content[0].text if result.content else ""
        flag = "ERR" if result.is_error else "OK"
    except Exception as exc:
        text, flag = str(exc), "EXC"
    print(f"\n{tool}:  [{flag}]")
    print(text[:400])


async def main() -> None:
    http = create_mcp_http_client(headers=_headers())
    async with streamable_http_client(URL, http_client=http) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            listed = await session.list_tools()
            print("tools served by ATLAS MCP server:")
            for t in listed.tools:
                print(f"  - {t.name}: {t.description.splitlines()[0]}")

            import datetime

            today = datetime.date.today().isoformat()
            days = [(datetime.date.today() + datetime.timedelta(days=i)).isoformat() for i in range(6)]

            await _call(session, "get_risk_snapshot", {"user_id": USER})
            await _call(session, "assess_affordability", {"user_id": USER, "amount_ngn": 120_000, "category": "electronics"})
            await _call(session, "log_transaction", {"user_id": USER, "amount_ngn": -25_000, "category": "food", "idempotency_key": "demo-food-1"})
            key = str(uuid.uuid4())
            await _call(session, "log_transaction", {"user_id": USER, "amount_ngn": -25_000, "category": "food", "idempotency_key": "demo-food-1"})
            plan = await session.call_tool(
                "plan_study_week",
                {
                    "user_id": USER,
                    "deadlines": [
                        {"title": "AI Systems Assignment", "due_at": f"{days[4]}T23:00:00", "weight": 3},
                        {"title": "Math Midterm", "due_at": f"{days[5]}T12:00:00", "weight": 2},
                    ],
                    "available_hours": [{"date": d, "start_hour": 18, "end_hour": 21} for d in days],
                },
            )
            print("\nplan_study_week:  [OK]")
            print((plan.content[0].text if plan.content else "")[:400])

            # The Alexa+ skill would pass the accepted blocks back; do that here.
            blocks = [
                {"title": "Study: AI Systems Assignment", "start_at": f"{days[0]}T18:00:00", "end_at": f"{days[0]}T19:30:00"},
                {"title": "Study: Math Midterm", "start_at": f"{days[0]}T20:00:00", "end_at": f"{days[0]}T21:30:00"},
            ]
            await _call(session, "commit_schedule", {"user_id": USER, "blocks": blocks, "idempotency_key": key})
            await _call(session, "commit_schedule", {"user_id": USER, "blocks": blocks, "idempotency_key": key})
            await _call(session, "get_daily_brief", {"user_id": USER, "date": today})
    await http.aclose()
    print("\ndemo walkthrough complete.")


if __name__ == "__main__":
    asyncio.run(main())