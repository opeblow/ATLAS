"""Bedrock-native tool schemas for the six ATLAS capabilities.

These mirror the tools served by the MCP server (mcp-server/src/atlas_mcp_server)
so the orchestrator, MCP transport, and Alexa+ skill all share one capability
contract. Kept as plain dicts so they can also feed the local fallback.
"""

TOOLS_SPEC: list[dict] = [
    {
        "toolSpec": {
            "name": "assess_affordability",
            "description": (
                "Check whether the user can afford a purchase right now, "
                "returning a safe/risky/blocked verdict, the subject risk "
                "change, and current balance."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "amount_ngn": {"type": "number", "description": "Purchase amount in NGN."},
                        "category": {"type": "string"},
                    },
                    "required": ["user_id", "amount_ngn"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_risk_snapshot",
            "description": (
                "Return the user's current financial risk level with the top "
                "contributing factors and current balance. Optionally compare "
                "with a 7-day window."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "window": {"type": "string", "enum": ["7d", "30d"]},
                    },
                    "required": ["user_id"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "log_transaction",
            "description": "Record a spend (negative) or income (positive) amount in the ledger.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "amount_ngn": {"type": "number"},
                        "category": {"type": "string"},
                        "ts": {"type": "string"},
                        "idempotency_key": {"type": "string"},
                    },
                    "required": ["user_id", "amount_ngn"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "plan_study_week",
            "description": (
                "Propose a study plan that spreads blocks of work across the "
                "user's availability ahead of each deadline."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "deadlines": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "due_at": {"type": "string"},
                                    "weight": {"type": "number"},
                                },
                            },
                        },
                        "available_hours": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "date": {"type": "string"},
                                    "start_hour": {"type": "integer"},
                                    "end_hour": {"type": "integer"},
                                },
                            },
                        },
                    },
                    "required": ["user_id", "deadlines", "available_hours"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "commit_schedule",
            "description": "Commit proposed calendar blocks to the user's real schedule.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "blocks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "start_at": {"type": "string"},
                                    "end_at": {"type": "string"},
                                },
                            },
                        },
                        "idempotency_key": {"type": "string"},
                    },
                    "required": ["user_id", "blocks"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_daily_brief",
            "description": (
                "Morning brief: today's balance + risk level + schedule and "
                "any deadlines approaching."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "date": {"type": "string"},
                    },
                    "required": ["user_id"],
                }
            },
        }
    },
]


def tool_names() -> list[str]:
    return [t["toolSpec"]["name"] for t in TOOLS_SPEC]