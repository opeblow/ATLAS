"""Alias so `python -m orchestrator.main` works; the real CLI is here."""

from __future__ import annotations

import argparse

from orchestrator import bedrock, fallback
from orchestrator import executor

FLAG_TOOL = {
    "afford": "assess_affordability",
    "risk": "get_risk_snapshot",
    "spent": "log_transaction",
    "plan": "plan_study_week",
    "commit": "commit_schedule",
    "brief": "get_daily_brief",
}


def run(utterance: str, user_id: str, force: str | None = None) -> dict:
    if force in FLAG_TOOL:
        memory = executor.SessionMemory()
        result = executor.execute_tool(FLAG_TOOL[force], {"user_id": user_id}, memory)
        return {"front_door": "forced", "tool": FLAG_TOOL[force], "answer": str(result)[:400], "tool_output": result}

    try:
        return bedrock.think(utterance, user_id=user_id)
    except bedrock.BedrockUnavailable as exc:
        print(f"[reasoning] Bedrock unavailable ({exc}); using local fallback.")
        return fallback.think(utterance, user_id=user_id)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--say", default="Good morning", help="Natural-language utterance to route.")
    ap.add_argument("--user", default="u_demo")
    ap.add_argument("--force", choices=list(FLAG_TOOL), help="Skip intent detection (demo shortcuts).")
    args = ap.parse_args()

    out = run(args.say, args.user, force=args.force)
    print(f"\n> {args.say}")
    print(f"[front door] {out['front_door']} | [tool] {out.get('tool', 'bedrock-tool-use')}")
    print(f"ATLAS: {out['answer']}")


if __name__ == "__main__":
    main()