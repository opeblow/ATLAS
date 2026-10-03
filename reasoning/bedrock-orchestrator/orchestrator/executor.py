"""Executes the six ATLAS capabilities against the REST backends.

Shared by the Bedrock tool-use loop and the local fallback router, so both
paths produce identical tool outcomes (and audit rows). Keeps a small
file-backed memory of the latest plan per user so a follow-up "commit it"
reuses the proposed blocks across CLI invocations.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field

import httpx

from atlas_common.audit import timed_tool_call

from orchestrator.tools_spec import tool_names

from atlas_common.config import settings

FINANCE_URL = settings.finance_url
SCHEDULING_URL = settings.scheduling_url
_TIMEOUT = httpx.Timeout(20.0)


def _state_path(user_id: str) -> str:
    d = os.path.join(tempfile.gettempdir(), "atlas_state")
    os.makedirs(d, exist_ok=True)
    user_key = hashlib.sha256(user_id.encode("utf-8")).hexdigest()
    return os.path.join(d, f"plan-{user_key}.json")


@dataclass
class SessionMemory:
    user_id: str = "u_demo"
    last_plan: dict | None = None
    last_blocks: list | None = None
    logs: list = field(default_factory=list)

    def _load(self) -> None:
        try:
            with open(_state_path(self.user_id), "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self.last_plan = data.get("plan")
            self.last_blocks = data.get("blocks") or []
        except FileNotFoundError:
            pass

    def remember_plan(self, plan: dict) -> None:
        self.last_plan = plan
        self.last_blocks = plan.get("proposed_blocks")
        with open(_state_path(self.user_id), "w", encoding="utf-8") as fh:
            json.dump({"plan": plan, "blocks": self.last_blocks}, fh)

    def plan_blocks(self) -> list:
        if not self.last_blocks:
            self._load()
        return self.last_blocks or []


def _post(url: str, payload: dict) -> dict:
    try:
        r = httpx.post(url, json=payload, timeout=_TIMEOUT)
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else {"error": f"{r.status_code}: {r.text[:200]}"}
    except Exception as exc:  # backend down -> structured error, agent still answers
        return {"error": f"backend unreachable: {exc}"}


def _get(url: str, params: dict | None = None) -> dict:
    try:
        r = httpx.get(url, params=params, timeout=_TIMEOUT)
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else {"error": f"{r.status_code}: {r.text[:200]}"}
    except Exception as exc:
        return {"error": f"backend unreachable: {exc}"}


def execute_tool(name: str, args: dict, memory: SessionMemory) -> dict:
    """Run one ATLAS capability. Returns the same JSON the MCP tools return."""
    user_id = args.get("user_id", "u_demo")
    with timed_tool_call(user_id, name, args):
        if name == "assess_affordability":
            return _post(f"{FINANCE_URL}/assess/affordability", args)
        if name == "get_risk_snapshot":
            return _get(f"{FINANCE_URL}/users/{user_id}/risk", {"window": args.get("window", "30d")})
        if name == "log_transaction":
            return _post(f"{FINANCE_URL}/transactions", args)
        if name == "plan_study_week":
            plan = _post(f"{SCHEDULING_URL}/plan/week", args)
            if isinstance(plan, dict) and not plan.get("error"):
                memory.remember_plan(plan)
            return plan
        if name == "commit_schedule":
            if not args.get("blocks"):
                args = {**args, "blocks": memory.plan_blocks()}
            return _post(f"{SCHEDULING_URL}/schedule/commit", args)
        if name == "get_daily_brief":
            day = args.get("date") or datetime.date.today().isoformat()
            finance = _get(f"{FINANCE_URL}/users/{user_id}/brief")
            time_brief = _get(f"{SCHEDULING_URL}/users/{user_id}/brief/{day}")
            return {"user_id": user_id, "date": day, **finance, **time_brief}
        return {"error": f"unknown tool {name}"}


def known_tools() -> list[str]:
    return tool_names()